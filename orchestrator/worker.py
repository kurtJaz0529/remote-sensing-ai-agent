"""Worker v0.1: newline JSON-RPC subprocess client, not an MCP implementation."""
import json
import subprocess
from contracts import canonical

class UncertainSubmission(RuntimeError):
    pass

class JsonWorker:
    def __init__(self, command, timeout=30):
        if not command or not isinstance(command, list):
            raise ValueError("worker command must be an argument list")
        self.command, self.timeout = command, timeout

    def request(self, method, params):
        request = dict(jsonrpc="2.0", id="request", method=method, params=params)
        try:
            result = subprocess.run(self.command, input=canonical(request)+"\n", text=True, encoding="utf-8", capture_output=True, timeout=self.timeout, check=False)
        except subprocess.TimeoutExpired:
            raise UncertainSubmission("worker timeout; query existing job before any new submission") from None
        if result.returncode:
            # Do not echo stderr: third-party worker logs may include credentials.
            raise UncertainSubmission("worker exited; inspect local worker logs and reconcile job")
        try:
            response = json.loads(result.stdout)
            if response["jsonrpc"] != "2.0" or response["id"] != "request" or "error" in response:
                raise ValueError()
            return response["result"]
        except (ValueError, KeyError, TypeError):
            raise UncertainSubmission("invalid worker reply; reconcile existing job") from None

    def submit(self, job):
        return self.request("workflow.submit", job)

    def status(self, job_id):
        return self.request("run.status", {"job_id":job_id})

    def cancel(self, job_id):
        return self.request("run.cancel", {"job_id":job_id})
