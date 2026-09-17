import fcntl
import hashlib
import json
import os
import platform
import plistlib
import shutil
import signal
import socket
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path


class KeyboardExtAXError(Exception):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def dictionary(self):
        error = {"code": self.code, "message": self.message}
        error.update(self.details)
        return {"ok": False, "error": error}


class KeyboardExtAXController:
    def __init__(self, project_root=None, cache_dir=None, developer_dir=None):
        self.project_root = Path(project_root or Path(__file__).resolve().parent / "harness")
        self.cache_dir = Path(
            cache_dir
            or os.environ.get("KEYBOARD_EXT_AX_CACHE_DIR")
            or Path.home() / "Library" / "Caches" / "KeyboardExtAX"
        )
        self.developer_dir = Path(
            developer_dir
            or os.environ.get("DEVELOPER_DIR")
            or self._selected_developer_dir()
        )
        self.xcodebuild = self.developer_dir / "usr" / "bin" / "xcodebuild"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def snapshot(self, simulator_udid, extension_bundle_id, raw=False):
        started = time.perf_counter()
        state, reused = self._ensure_session(simulator_udid)
        if not reused:
            return self._refocus_required(simulator_udid, started)
        request = {
            "id": int(time.time() * 1_000),
            "command": "snapshot",
            "extension_bundle_id": extension_bundle_id,
            "raw": raw,
        }
        try:
            response = self._send(state["port"], request, timeout=30)
        except (ConnectionError, OSError, TimeoutError):
            self.stop(simulator_udid)
            self._ensure_session(simulator_udid)
            return self._refocus_required(simulator_udid, started)

        response["session_reused"] = reused
        response["total_ms"] = (time.perf_counter() - started) * 1_000
        if raw or not response.get("ok"):
            return response
        return self._compact(response)

    def status(self, simulator_udid=None):
        states = []
        session_root = self.cache_dir / "sessions"
        if not session_root.exists():
            return {"ok": True, "sessions": states}

        state_files = [self._session_dir(simulator_udid) / "state.json"] if simulator_udid else session_root.glob("*/state.json")
        for state_file in state_files:
            state = self._read_json(state_file)
            if not state:
                continue
            healthy = self._state_healthy(state)
            states.append(
                {
                    "simulator_udid": state.get("simulator_udid"),
                    "pid": state.get("pid"),
                    "healthy": healthy,
                    "started_at": state.get("started_at"),
                    "log": state.get("log"),
                }
            )
        return {"ok": True, "sessions": states}

    def stop(self, simulator_udid):
        session_dir = self._session_dir(simulator_udid)
        with self._lock(session_dir / "session.lock"):
            state = self._read_json(session_dir / "state.json")
            if not state:
                return {"ok": True, "stopped": False, "simulator_udid": simulator_udid}
            self._stop_state(state)
            (session_dir / "state.json").unlink(missing_ok=True)
            return {"ok": True, "stopped": True, "simulator_udid": simulator_udid}

    def stop_all(self):
        session_root = self.cache_dir / "sessions"
        stopped = []
        if session_root.exists():
            for state_file in session_root.glob("*/state.json"):
                state = self._read_json(state_file)
                if state and state.get("simulator_udid"):
                    result = self.stop(state["simulator_udid"])
                    if result["stopped"]:
                        stopped.append(state["simulator_udid"])
        return {"ok": True, "stopped": stopped}

    def _ensure_session(self, simulator_udid):
        build = self._ensure_build(simulator_udid)
        session_dir = self._session_dir(simulator_udid)
        session_dir.mkdir(parents=True, exist_ok=True)

        with self._lock(session_dir / "session.lock"):
            state_file = session_dir / "state.json"
            state = self._read_json(state_file)
            if state and state.get("build_key") == build["key"] and self._state_healthy(state):
                return state, True
            if state:
                self._stop_state(state)
                state_file.unlink(missing_ok=True)

            port = self._free_port()
            configured_plan = self._configure_test_plan(
                Path(build["xctestrun"]),
                simulator_udid,
                port,
            )
            result_bundle = session_dir / "result.xcresult"
            shutil.rmtree(result_bundle, ignore_errors=True)
            log_path = session_dir / "runner.log"
            log = log_path.open("wb")
            command = [
                str(self.xcodebuild),
                "-xctestrun",
                str(configured_plan),
                "-destination",
                f"platform=iOS Simulator,id={simulator_udid}",
                "-parallel-testing-enabled",
                "NO",
                "-only-testing:KeyboardExtAXUITests/PersistentKeyboardExtAXTests/testServeSnapshots",
                "-resultBundlePath",
                str(result_bundle),
                "test-without-building",
            ]
            process = subprocess.Popen(
                command,
                cwd=self.project_root,
                env=self._xcode_environment(),
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            log.close()
            state = {
                "simulator_udid": simulator_udid,
                "pid": process.pid,
                "port": port,
                "build_key": build["key"],
                "xctestrun": str(configured_plan),
                "log": str(log_path),
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            self._write_json(state_file, state)

            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                if self._ping(state):
                    return state, False
                time.sleep(0.25)

            self._stop_state(state)
            state_file.unlink(missing_ok=True)
            tail = self._tail(log_path)
            raise KeyboardExtAXError(
                "runner_start_failed",
                "persistent XCTest runner did not become ready",
                {"log": str(log_path), "log_tail": tail},
            )

    def _ensure_build(self, simulator_udid):
        key = self._build_key()
        build_dir = self.cache_dir / "builds" / key
        with self._lock(self.cache_dir / "build.lock"):
            plans = list((build_dir / "Build" / "Products").glob("KeyboardExtAX_*.xctestrun"))
            if len(plans) == 1:
                return {"key": key, "xctestrun": str(plans[0])}

            build_dir.mkdir(parents=True, exist_ok=True)
            log_path = build_dir / "build.log"
            command = [
                str(self.xcodebuild),
                "-project",
                str(self.project_root / "KeyboardExtAX.xcodeproj"),
                "-scheme",
                "KeyboardExtAX",
                "-destination",
                f"platform=iOS Simulator,id={simulator_udid}",
                "-derivedDataPath",
                str(build_dir),
                "-parallel-testing-enabled",
                "NO",
                "build-for-testing",
            ]
            with log_path.open("wb") as log:
                result = subprocess.run(
                    command,
                    cwd=self.project_root,
                    env=self._xcode_environment(),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
            plans = list((build_dir / "Build" / "Products").glob("KeyboardExtAX_*.xctestrun"))
            if result.returncode != 0 or len(plans) != 1:
                raise KeyboardExtAXError(
                    "build_failed",
                    "could not build KeyboardExtAX",
                    {"log": str(log_path), "log_tail": self._tail(log_path)},
                )
            return {"key": key, "xctestrun": str(plans[0])}

    def _configure_test_plan(self, source, simulator_udid, port):
        with source.open("rb") as file:
            plan = plistlib.load(file)
        plan["KeyboardExtAXUITests"]["EnvironmentVariables"]["KEYBOARD_EXT_AX_PORT"] = str(port)
        destination = source.with_name(f"KeyboardExtAX-{simulator_udid}.xctestrun")
        with destination.open("wb") as file:
            plistlib.dump(plan, file)
        return destination

    def _state_healthy(self, state):
        return (
            self._pid_alive(state.get("pid"))
            and self._owns_process(state)
            and self._ping(state)
        )

    def _ping(self, state):
        try:
            response = self._send(
                state["port"],
                {"id": int(time.time() * 1_000), "command": "ping"},
                timeout=1,
            )
            return response.get("ok") and response.get("simulator_udid") == state.get("simulator_udid")
        except (ConnectionError, OSError, TimeoutError, ValueError):
            return False

    def _stop_state(self, state):
        if self._ping(state):
            try:
                self._send(
                    state["port"],
                    {"id": int(time.time() * 1_000), "command": "shutdown"},
                    timeout=3,
                )
            except (ConnectionError, OSError, TimeoutError, ValueError):
                pass
        deadline = time.monotonic() + 8
        while self._pid_alive(state.get("pid")) and time.monotonic() < deadline:
            time.sleep(0.1)
        if self._pid_alive(state.get("pid")) and self._owns_process(state):
            try:
                os.killpg(state["pid"], signal.SIGTERM)
            except ProcessLookupError:
                pass

    def _owns_process(self, state):
        pid = state.get("pid")
        if not pid:
            return False
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
        )
        command = result.stdout
        return "xcodebuild" in command and state.get("xctestrun", "") in command

    @staticmethod
    def _pid_alive(pid):
        if not pid:
            return False
        try:
            os.kill(pid, 0)
            return True
        except (OSError, TypeError):
            return False

    @staticmethod
    def _send(port, request, timeout):
        started = time.perf_counter()
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as connection:
            connection.settimeout(timeout)
            connection.sendall(json.dumps(request).encode() + b"\n")
            chunks = []
            while True:
                chunk = connection.recv(65_536)
                if not chunk:
                    break
                chunks.append(chunk)
        payload = b"".join(chunks)
        if not payload:
            raise ConnectionError("server closed the connection without a response")
        response = json.loads(payload)
        response["round_trip_ms"] = (time.perf_counter() - started) * 1_000
        return response

    @staticmethod
    def _refocus_required(simulator_udid, started):
        return {
            "ok": False,
            "error": {
                "code": "client_refocus_required",
                "message": "XCTest runner started; refocus the client text field and retry",
            },
            "simulator_udid": simulator_udid,
            "session_reused": False,
            "total_ms": (time.perf_counter() - started) * 1_000,
        }

    @staticmethod
    def _compact(response):
        tree = response.get("tree")
        if not isinstance(tree, dict):
            return response
        return {
            "ok": True,
            "snapshot_id": response.get("snapshot_id"),
            "simulator_udid": response.get("simulator_udid"),
            "extension_bundle_id": response.get("extension_bundle_id"),
            "pid": response.get("pid"),
            "elapsed_ms": response.get("elapsed_ms"),
            "round_trip_ms": response.get("round_trip_ms"),
            "session_reused": response.get("session_reused"),
            "total_ms": response.get("total_ms"),
            "elements": KeyboardExtAXController._flatten(tree),
        }

    @staticmethod
    def _flatten(node, ref="0"):
        center = node.get("center")
        element = {
            "ref": ref,
            "type": node["type"],
            "identifier": node.get("identifier"),
            "label": node.get("label"),
            "frame": node.get("frame"),
            "center": center,
            "tap_x": int(center["x"] + 0.5) if isinstance(center, dict) else None,
            "tap_y": int(center["y"] + 0.5) if isinstance(center, dict) else None,
        }
        elements = [element]
        for index, child in enumerate(node.get("children", [])):
            elements.extend(KeyboardExtAXController._flatten(child, f"{ref}.{index}"))
        return elements

    def _build_key(self):
        digest = hashlib.sha256()
        digest.update(self._xcode_version().encode())
        digest.update(platform.machine().encode())
        paths = [
            self.project_root / "project.yml",
            self.project_root / "KeyboardExtAX.xcodeproj" / "project.pbxproj",
            *sorted((self.project_root / "Host").glob("*.swift")),
            *sorted((self.project_root / "UITests").glob("*.swift")),
        ]
        for path in paths:
            digest.update(str(path.relative_to(self.project_root)).encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()[:16]

    def _xcode_version(self):
        result = subprocess.run(
            [str(self.xcodebuild), "-version"],
            env=self._xcode_environment(),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise KeyboardExtAXError("xcode_unavailable", "could not read Xcode version")
        return result.stdout

    def _xcode_environment(self):
        environment = os.environ.copy()
        environment["DEVELOPER_DIR"] = str(self.developer_dir)
        return environment

    def _session_dir(self, simulator_udid):
        return self.cache_dir / "sessions" / simulator_udid

    @staticmethod
    def _selected_developer_dir():
        result = subprocess.run(["xcode-select", "-p"], capture_output=True, text=True)
        if result.returncode != 0:
            raise KeyboardExtAXError("xcode_unavailable", "xcode-select did not return a developer directory")
        return result.stdout.strip()

    @staticmethod
    def _free_port():
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            return server.getsockname()[1]

    @staticmethod
    def _tail(path, lines=30):
        try:
            return "\n".join(path.read_text(errors="replace").splitlines()[-lines:])
        except OSError:
            return ""

    @staticmethod
    def _read_json(path):
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _write_json(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, indent=2) + "\n")
        temporary.replace(path)

    @staticmethod
    @contextmanager
    def _lock(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
