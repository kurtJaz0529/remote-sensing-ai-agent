"""SQLite keyword index; applicability is filtered before ranking."""
import json
import re
import sqlite3
from pathlib import Path
from packaging.specifiers import SpecifierSet, InvalidSpecifier
from packaging.version import Version, InvalidVersion
from contracts import canonical, fingerprint, validate

def compatible(scope, version):
    if not version or not scope:
        return False
    if scope.startswith("exact:"):
        return version == scope[6:]
    try:
        return Version(version) in SpecifierSet(scope)
    except (InvalidSpecifier,InvalidVersion):
        return False

class KnowledgeIndex:
    def __init__(self, path, reviewed_evidence=None):
        path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path)
        self.db.row_factory=sqlite3.Row
        self.reviewed_evidence=reviewed_evidence or {}
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, body TEXT);
        CREATE TABLE IF NOT EXISTS knowledge(id TEXT,revision INTEGER,body TEXT,PRIMARY KEY(id,revision));
        CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(id UNINDEXED, revision UNINDEXED, text, tokenize='unicode61');
        ''')

    def close(self):
        self.db.close()

    def ingest(self, records, sources):
        # Entire batch validated before modifying the index.
        source_map={}
        for source in sources:
            validate("source",source)
            source_map[source["source_id"]]=source
        known={row[0]:json.loads(row[1]) for row in self.db.execute("SELECT id,body FROM sources")}
        known.update(source_map)
        for record in records:
            validate("knowledge",record)
            if record["kind"] not in ("software_method","method","parameter","error","workflow"):
                raise ValueError("runtime knowledge kind excludes held-out answers/case labels")
            if any(s not in known for s in record["source_ids"]):
                raise ValueError("unknown source ID")
            if record["lifecycle"]=="published":
                if record["source_review_status"]!="verified" or record["local_verification_status"]!="verified" or not record["verification_run_ids"] or not record["reviewer_role"]:
                    raise ValueError("publication needs source review, real-run references and reviewer")
                if any(known[s]["review_status"]!="verified" for s in record["source_ids"]):
                    raise ValueError("unverified source cannot support publication")
                for run in record["verification_run_ids"]:
                    proof=self.reviewed_evidence.get(run,{})
                    if proof.get("mode")!="real" or not proof.get("passed") or not proof.get("evidence_manifest_sha256"):
                        raise ValueError("published knowledge needs reviewed real evidence catalog: "+run)
            if not record["software_version_scope"].startswith("exact:"):
                scope=record["software_version_scope"]
                if not scope:
                    raise ValueError("software version scope required; unknown cannot publish")
                SpecifierSet(scope)
        with self.db:
            for source in sources:
                existing=self.db.execute("SELECT body FROM sources WHERE id=?",(source["source_id"],)).fetchone()
                if existing and existing[0]!=canonical(source):
                    raise ValueError("source immutable; assign new source ID")
                self.db.execute("INSERT OR IGNORE INTO sources VALUES(?,?)",(source["source_id"],canonical(source)))
            for record in records:
                old=self.db.execute("SELECT body FROM knowledge WHERE id=? AND revision=?",(record["knowledge_id"],record["revision"])).fetchone()
                if old:
                    if old[0]!=canonical(record):
                        raise ValueError("knowledge revision immutable")
                    continue
                self.db.execute("INSERT INTO knowledge VALUES(?,?,?)",(record["knowledge_id"],record["revision"],canonical(record)))
                self.db.execute("INSERT INTO search VALUES(?,?,?)",(record["knowledge_id"],record["revision"],record["claim"]+" "+record["source_locator"]))

    def search(self, query, software, version, licenses=(), product=None, input_format=None, include_candidates=False, limit=10):
        if not query.strip() or limit<1 or limit>100:
            raise ValueError("nonempty query and limit 1..100 required")
        latest=self.db.execute("SELECT k.body FROM knowledge k JOIN (SELECT id,MAX(revision) revision FROM knowledge GROUP BY id) n ON k.id=n.id AND k.revision=n.revision").fetchall()
        # FTS5 for token matches; exact substring supplements CJK/error/function IDs.
        terms=re.findall(r"[\w]+",query,flags=re.UNICODE)
        match=" OR ".join('"'+term.replace('"','""')+'"' for term in terms)
        ranks={}
        if match:
            for row in self.db.execute("SELECT id,revision,bm25(search) score FROM search WHERE search MATCH ?",(match,)):
                ranks[(row[0],row[1])]=row[2]
        result=[]
        for row in latest:
            record=json.loads(row[0])
            if record["software"]!=software or not compatible(record["software_version_scope"],version):
                continue
            if not set(record["required_licenses"])<=set(licenses):
                continue
            if record["sensor_product_scope"] and product not in record["sensor_product_scope"]:
                continue
            if record["input_formats"] and input_format not in record["input_formats"]:
                continue
            published=record["lifecycle"]=="published" and record["source_review_status"]=="verified" and record["local_verification_status"]=="verified"
            if not published and not include_candidates:
                continue
            if record["lifecycle"]=="withdrawn":
                continue
            text=(record["claim"]+" "+record["source_locator"]+" "+record["knowledge_id"]).casefold()
            exact=query.casefold() in text
            key=(record["knowledge_id"],record["revision"])
            if not exact and key not in ranks:
                continue
            sources=[json.loads(self.db.execute("SELECT body FROM sources WHERE id=?",(sid,)).fetchone()[0]) for sid in record["source_ids"]]
            result.append({**record,"sources":sources,"execution_eligible":published and not record["conflicts_with"],"score":(100 if exact else 0)-ranks.get(key,0),"conflict_requires_review":bool(record["conflicts_with"])})
        return sorted(result,key=lambda r:(-r["score"],r["knowledge_id"]))[:limit]

    def snapshot(self, destination):
        body={"schema_revision":"0.1.0","sources":[json.loads(r[0]) for r in self.db.execute("SELECT body FROM sources ORDER BY id")],"knowledge":[json.loads(r[0]) for r in self.db.execute("SELECT body FROM knowledge ORDER BY id,revision")]}
        result={"sha256":fingerprint(body),"snapshot":body}
        Path(destination).write_text(canonical(result),encoding="utf-8")
        return result["sha256"]

    def restore(self, path):
        snapshot=json.loads(Path(path).read_text(encoding="utf-8"))
        if fingerprint(snapshot["snapshot"])!=snapshot["sha256"]:
            raise ValueError("snapshot hash mismatch")
        self.ingest(snapshot["snapshot"]["knowledge"],snapshot["snapshot"]["sources"])
