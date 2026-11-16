import multiprocessing
import time


_POLL_INTERVAL_SECONDS = 0.1


class WorkerError(Exception):

    def __init__(self, message, elapsed_ms):
        super().__init__(message)
        self.elapsed_ms = elapsed_ms


class WorkerTimeout(WorkerError):

    def __init__(self, elapsed_ms):
        super().__init__("Benchmark watchdog expired.", elapsed_ms)


class Worker:
    def __init__(self, handler):
        self.handler = handler
        self.context = multiprocessing.get_context("spawn")
        self.process = None
        self.connection = None
        self._start()

    def _start(self):
        parent, child = self.context.Pipe(duplex=True)
        process = self.context.Process(
            target=_worker_main,
            args=(child, self.handler),
            daemon=True
        )
        process.start()
        child.close()
        self.process = process
        self.connection = parent
        if not parent.poll(10) or parent.recv() != "ready":
            self._stop(force=True)
            raise RuntimeError("Benchmark worker did not start.")

    def run(self, payload, hard_timeout_ms):
        try:
            self.connection.send(payload)
        except (BrokenPipeError, EOFError, OSError):
            self._restart()
            self.connection.send(payload)

        start = time.perf_counter()
        deadline = start + hard_timeout_ms / 1000
        while True:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                elapsed_ms = (time.perf_counter() - start) * 1000
                self._restart(force=True)
                raise WorkerTimeout(elapsed_ms)

            wait = min(_POLL_INTERVAL_SECONDS, remaining)
            try:
                if self.connection.poll(wait):
                    result = self.connection.recv()
                    return result
            except (EOFError, OSError):
                exitcode = self.process.exitcode
                elapsed_ms = (time.perf_counter() - start) * 1000
                self._restart(force=True)
                raise WorkerError(
                    f"Benchmark worker exited unexpectedly (exit code {exitcode}).",
                    elapsed_ms
                )

            if not self.process.is_alive():
                exitcode = self.process.exitcode
                elapsed_ms = (time.perf_counter() - start) * 1000
                self._restart(force=True)
                raise WorkerError(
                    f"Benchmark worker exited unexpectedly (exit code {exitcode}).",
                    elapsed_ms
                )

    def _restart(self, force=False):
        self._stop(force=force)
        self._start()

    def _stop(self, force=False):
        process = self.process
        connection = self.connection
        self.process = None
        self.connection = None

        if process is None:
            return

        if not force and process.is_alive() and connection is not None:
            try:
                connection.send(None)
            except (BrokenPipeError, EOFError, OSError):
                pass
            process.join(timeout=0.5)

        if process.is_alive():
            process.terminate()
            process.join(timeout=1)
        if process.is_alive() and hasattr(process, "kill"):
            process.kill()
            process.join(timeout=1)

        if connection is not None:
            try:
                connection.close()
            except OSError:
                pass
        process.close()

    def close(self):
        self._stop(force=False)


def _worker_main(connection, handler):
    try:
        connection.send("ready")
        while True:
            message = connection.recv()
            if message is None:
                return
            result = handler(*message)
            connection.send(result)
    except (EOFError, BrokenPipeError, OSError):
        return
    finally:
        try:
            connection.close()
        except OSError:
            pass

