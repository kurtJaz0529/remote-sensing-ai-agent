"""Coordinator MCP client; reconnecting never implies a job resubmission."""
import asyncio
import json
import tempfile
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from .worker import UncertainSubmission


class McpWorker:
    def __init__(self, command, timeout=30):
        if not command or not isinstance(command, (list,str)):
            raise ValueError('MCP server command must be an argument list')
        self.command, self.timeout = command, timeout

    async def _request(self, name, params):
        with tempfile.TemporaryFile(mode='w+',encoding='utf-8') as errlog:
            return await self._exchange(name,params,errlog)

    async def _exchange(self, name, params, errlog):
        if isinstance(self.command,str):
            async with asyncio.timeout(self.timeout):
                async with streamable_http_client(self.command) as (read,write,_):
                    async with ClientSession(read,write) as session:
                        await session.initialize()
                        reply = await session.call_tool(name,params)
                        if reply.isError:
                            raise UncertainSubmission('MCP tool error; reconcile original job')
                        return reply.structuredContent if reply.structuredContent is not None else json.loads(next(c.text for c in reply.content if c.type=='text'))
        server = StdioServerParameters(command=self.command[0],args=self.command[1:])
        async with asyncio.timeout(self.timeout):
            async with stdio_client(server,errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    reply = await session.call_tool(name, params)
                    if reply.isError:
                        raise UncertainSubmission('MCP tool error; reconcile original job')
                    if reply.structuredContent is not None:
                        return reply.structuredContent
                    return json.loads(next(c.text for c in reply.content if c.type=='text'))

    def request(self, name, params):
        try:
            return asyncio.run(self._request(name,params))
        except Exception:
            # Do not disclose external errors/logs or silently retry writes.
            raise UncertainSubmission('MCP response uncertain; query original job before retry') from None

    def submit(self, job):
        return self.request('workflow_submit', {'job':job})

    def status(self, job_id):
        return self.request('run_status', {'job_id':job_id})

    def cancel(self, job_id):
        return self.request('run_cancel', {'job_id':job_id})
