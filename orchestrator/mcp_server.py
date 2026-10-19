"""MCP stdio boundary for durable, evidence-gated local native jobs."""
import argparse
import json
from mcp.server.fastmcp import FastMCP
from .local_worker import LocalWorker


def create_server(root, durable=False, port=8765):
    server = FastMCP('rsagent-local-worker',host='127.0.0.1',port=port,log_level='WARNING')

    def invoke(method, value):
        worker = LocalWorker(root)
        try:
            return getattr(worker, method)(value)
        finally:
            worker.close()

    @server.tool()
    def workflow_submit(job: dict) -> dict:
        """Submit a frozen and confirmed job; duplicate payloads return the original job."""
        if not durable:
            raise ValueError('Async submissions require the persistent HTTP MCP service; stdio client shutdown kills descendants on Windows')
        return invoke('submit', job)

    @server.tool()
    def run_status(job_id: str) -> dict:
        """Query an existing job; never creates or replays unknown jobs."""
        return invoke('status', job_id)

    @server.tool()
    def run_cancel(job_id: str) -> dict:
        """Request cancellation; running jobs confirm cancellation asynchronously."""
        return invoke('cancel', job_id)

    @server.tool()
    def registered_input_audit(task_id: str, revision: int, approval_id: str) -> dict:
        """Read-only PNG integrity audit over inputs bound to an approved plan."""
        from .image_audit import registered_image_audit
        return registered_image_audit(root,task_id,revision,approval_id)

    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--http',action='store_true')
    parser.add_argument('--port',type=int,default=8765)
    args = parser.parse_args()
    create_server(args.root,durable=args.http,port=args.port).run(transport='streamable-http' if args.http else 'stdio')


if __name__ == '__main__':
    main()
