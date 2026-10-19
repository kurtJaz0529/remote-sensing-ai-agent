"""Two fixed MCP provider probes; never uploads user imagery or executes tool proposals."""
import argparse
import os
import json
import struct
import sys
import zlib
from pathlib import Path
from contracts import canonical, fingerprint, sha256
from orchestrator.providers import Provider, ProviderError
from orchestrator.store import Store, now


def fixture_png():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 32, 32, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress((b'\0' + b'\xff\0\0' * 32) * 32)) + chunk(b'IEND', b'')


def run_probe(root, kind):
    if kind not in ('tool', 'vision'):
        raise ValueError('Only fixed tool and synthetic vision probes are allowed')
    root = Path(root)
    profile = json.loads((root / 'profile.json').read_text(encoding='utf-8'))
    if fingerprint(profile) != (root / 'profile.sha256').read_text().strip():
        raise ValueError('Probe configuration changed')
    store = Store(root)
    provider = None
    try:
        store.db.execute('CREATE TABLE IF NOT EXISTS probe_claims(kind TEXT PRIMARY KEY, body TEXT)')
        with store.coordinator_lock():
            row = store.db.execute('SELECT body FROM probe_claims WHERE kind=?', (kind,)).fetchone()
            if row:
                return json.loads(row[0])  # started/unknown is not permission to repeat a billed call
            with store.db:
                store.db.execute('INSERT INTO probe_claims VALUES(?,?)', (kind, canonical(dict(status='started', kind=kind, profile_hash=fingerprint(profile), started_at=now(), retry_count=0))))
        provider = Provider(profile, store)
        try:
            if kind == 'tool':
                result = provider.probe()
            else:
                fixture = root / 'synthetic-red.png'
                if fixture.read_bytes() != fixture_png():
                    raise ValueError('Synthetic fixture changed')
                result = provider.probe_vision(fixture, 'red')
            result.update(status='completed', kind=kind, profile_hash=fingerprint(profile), retry_count=0,
                          scope='single endpoint/configuration probe; no user files; no tool execution',
                          cost_note='Peak/cache-miss rate estimate, not an invoice')
        except ProviderError as exc:
            result = dict(status='failed', kind=kind, error_kind=exc.kind, message=str(exc), retry_count=0)
        with store.db:
            store.db.execute('UPDATE probe_claims SET body=? WHERE kind=?', (canonical(result), kind))
        return result
    finally:
        if provider:
            provider.close()
        store.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--serve', action='store_true')
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if args.serve:
        from mcp.server.fastmcp import FastMCP
        server = FastMCP('rsagent-fixed-provider-probes', log_level='WARNING')
        @server.tool()
        def provider_probe(kind: str) -> dict:
            """One idempotent fixed probe; synthetic pixels only; no arbitrary prompts/paths."""
            return run_probe(root, kind)
        server.run()
        return
    if root.exists():
        raise ValueError('Use a fresh probe directory; inspect existing claims instead of retrying')
    root.mkdir(parents=True)
    profile = dict(schema_revision='0.1.0', provider='deepseek', base_url='https://api.deepseek.com', model='deepseek-flash',
                   api_key_env='DEEPSEEK_API_KEY', timeout_seconds=45, context_tokens=8192, tool_calling='unknown', vision='unknown',
                   extra_body={'thinking': {'type': 'disabled'}}, pricing=dict(input_per_million=0.3, output_per_million=1.2,
                   currency='USD', source_url='https://api-docs.deepseek.com/quick_start/pricing/'))
    (root / 'profile.json').write_text(canonical(profile), encoding='utf-8')
    (root / 'profile.sha256').write_text(fingerprint(profile), encoding='ascii')
    (root / 'synthetic-red.png').write_bytes(fixture_png())
    from orchestrator.mcp_worker import McpWorker
    # MCP SDK inherits only a minimal environment. Explicitly pass this one credential
    # through process memory; never add it to the profile, evidence, output or logs.
    credential_env = {name: os.environ[name] for name in ('DEEPSEEK_API_KEY',) if name in os.environ}
    client = McpWorker([sys.executable, '-m', 'scripts.probe_provider_mcp', '--serve', '--root', str(root)], timeout=55, env=credential_env)
    results = []
    for kind in ('tool', 'vision'):
        result = client.request('provider_probe', {'kind': kind})
        results.append(result)
        (root / (kind + '-result.json')).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        if result.get('status') != 'completed':
            break
    print(json.dumps(dict(results=results, fixture_sha256=sha256(root / 'synthetic-red.png')), indent=2))


if __name__ == '__main__':
    main()
