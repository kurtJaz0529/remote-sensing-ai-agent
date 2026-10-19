import asyncio
import importlib.util
import json
import sys
import time
import socket
import subprocess
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from orchestrator.engine import Engine
from orchestrator.examples import mock_plan
from orchestrator.intake import inventory


@unittest.skipUnless(importlib.util.find_spec('mcp'), 'Install the mcp extra')
class McpIntegrationTests(unittest.TestCase):
    def test_handshake_tools_submit_status_and_reconnect(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from orchestrator.mcp_worker import McpWorker
        with TemporaryDirectory() as tmp:
            service = None
            inputs=Path(tmp)/'inputs';inputs.mkdir();(inputs/'fixture.txt').write_text('synthetic')
            runtime=Path(tmp)/'runtime';engine=Engine(runtime)
            try:
                manifest=inventory(inputs,'SYNTHETIC');plan=mock_plan(manifest)
                engine.save_plan(plan,manifest,inputs)
                approval=engine.approve(plan['task_id'],1,'test fixture')
                run=engine.create_run(plan['task_id'],1,approval,'mock')
                cmd=[sys.executable,'-m','orchestrator.mcp_server','--root',str(runtime)]
                async def discovery():
                    async with stdio_client(StdioServerParameters(command=cmd[0],args=cmd[1:])) as (read,write):
                        async with ClientSession(read,write) as session:
                            await session.initialize()
                            return {t.name for t in (await session.list_tools()).tools}
                self.assertEqual(asyncio.run(discovery()),{'workflow_submit','run_status','run_cancel','registered_input_audit'})
                with socket.socket() as listener:
                    listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
                log=(Path(tmp)/'mcp.log').open('wb')
                service=subprocess.Popen(cmd+['--http','--port',str(port)],stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
                deadline=time.monotonic()+15
                while True:
                    try:
                        with socket.create_connection(('127.0.0.1',port),timeout=.1):break
                    except OSError:
                        if time.monotonic()>deadline:raise
                        time.sleep(.1)
                client=McpWorker(f'http://127.0.0.1:{port}/mcp')
                engine.execute(run,client)
                job=json.loads(engine.store.db.execute('select body from steps').fetchone()[0])
                deadline=time.monotonic()+20
                while client.status(job['job_id'])['status'] in ('queued','running') and time.monotonic()<deadline:
                    time.sleep(.1)
                self.assertEqual(engine.execute(run,client)['state'],'Completed')
                self.assertEqual(client.submit(job)['status'],'succeeded')
                self.assertEqual(client.cancel(job['job_id'])['status'],'succeeded')
            finally:
                engine.store.close()
                if service is not None:
                    service.terminate();service.wait(timeout=10);log.close()
