"""Versioned experience workflow. No executable rules are enabled automatically."""
import json
import sqlite3
from contracts import canonical, validate

class ExperienceRegistry:
    def __init__(self, path):
        self.db=sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS experience(id TEXT,revision INTEGER,body TEXT,PRIMARY KEY(id,revision))")

    def save(self, record, evidence_catalog):
        validate("experience",record)
        old=self.db.execute("SELECT body FROM experience WHERE id=? ORDER BY revision DESC LIMIT 1",(record["experience_id"],)).fetchone()
        previous=json.loads(old[0]) if old else None
        stages={"candidate":0,"reproduced":1,"fix_verified":2,"published":3,"withdrawn":4}
        stage=stages[record["status"]]
        if previous:
            if record["revision"]<=previous["revision"] or record["supersedes"]!=previous["revision"]:
                raise ValueError("new revision must supersede latest revision")
            restarting=previous["status"]=="withdrawn" and record["status"]=="candidate"
            if stage!=4 and stage!=stages[previous["status"]]+1 and not restarting:
                raise ValueError("experience stages cannot be skipped")
        elif record["revision"]!=1 or stage!=0 or record["supersedes"] is not None:
            raise ValueError("first experience must be candidate revision 1")
        required=["evidence_run_ids"]
        if stage>=1 and stage!=4: required.append("reproduction_run_ids")
        if stage>=2 and stage!=4: required.append("fix_comparison_run_ids")
        if stage>=3 and stage!=4: required.append("regression_run_ids")
        for key in required:
            if not record[key]:
                raise ValueError("missing evidence: "+key)
            for run in record[key]:
                proof=evidence_catalog.get(run,{})
                if proof.get("mode")!="real" or not proof.get("passed") or not proof.get("evidence_manifest_sha256"):
                    raise ValueError("real validated run manifest required: "+run)
        if record["status"]=="published" and (not record["reviewer_role"] or record["reviewer_role"]==record["author_role"]):
            raise ValueError("independent reviewer required")
        with self.db:
            self.db.execute("INSERT INTO experience VALUES(?,?,?)",(record["experience_id"],record["revision"],canonical(record)))

    def active(self):
        return [r for (body,) in self.db.execute("SELECT e.body FROM experience e JOIN (SELECT id,MAX(revision) rev FROM experience GROUP BY id) n ON e.id=n.id AND e.revision=n.rev") if (r:=json.loads(body))["status"]=="published"]

    def close(self):
        self.db.close()
