"""OpenAI/DeepSeek Chat Completions adapter. Never executes model proposals."""
import base64
import json
import math
import os
import time
from urllib.parse import urlparse
import httpx
from jsonschema import Draft202012Validator
from contracts import VERSION, canonical, validate
from .store import now

class ProviderError(RuntimeError):
    def __init__(self, kind, message):
        super().__init__(message)
        self.kind=kind

def strict_json(value):
    def pairs(items):
        result={}
        for key,val in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key]=val
        return result
    return json.loads(value, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))

class Provider:
    def __init__(self, config, store=None, transport=None):
        validate("provider", config)
        url=urlparse(config["base_url"])
        if url.scheme!="https" or not url.netloc or url.username or url.password or url.query or url.fragment:
            raise ValueError("provider needs an HTTPS base URL without embedded credentials/query")
        if set(config["extra_body"]) & {"model","messages","tools","tool_choice","stream","max_tokens","max_completion_tokens"}:
            raise ValueError("extra_body cannot override protocol fields")
        self.config, self.store=config,store
        self.client=httpx.Client(timeout=config["timeout_seconds"],transport=transport,follow_redirects=False)

    def close(self):
        self.client.close()

    def _record(self, record, entry_id=None):
        if self.store:
            with self.store.db:
                if entry_id is None:
                    cursor=self.store.db.execute("INSERT INTO usage(provider,model,timestamp,body) VALUES(?,?,?,?)",(self.config["provider"],self.config["model"],now(),canonical(record)))
                    return cursor.lastrowid
                self.store.db.execute("UPDATE usage SET body=? WHERE seq=?",(canonical(record),entry_id))

    def _spent(self, scope, max_cost, external_used):
        if max_cost is None:
            return external_used
        if self.store is None:
            raise ProviderError("budget","bounded model calls require a persistent usage store")
        spent=external_used
        currency=(self.config["pricing"] or {}).get("currency")
        for (body,) in self.store.db.execute("SELECT body FROM usage"):
            record=json.loads(body)
            if record.get("budget_scope")==scope:
                if record.get("cost") is None or record.get("currency")!=currency:
                    raise ProviderError("budget","prior request cost is unknown or currency changed; reconcile before continuing")
                spent+=record["cost"]
        return spent

    def _budget(self, body, max_cost, used_cost):
        pricing=self.config["pricing"]
        if max_cost is None:
            return
        if not math.isfinite(max_cost) or max_cost < 0 or used_cost is None:
            raise ProviderError("budget","unknown prior usage/cost prevents a bounded call")
        if not pricing or not all(k in pricing for k in ("input_per_million","output_per_million","source_url","currency")):
            raise ProviderError("budget","pricing with currency and source is required for a cost limit")
        rates=[pricing["input_per_million"],pricing["output_per_million"]]
        if any(not isinstance(x,(int,float)) or not math.isfinite(x) or x<0 for x in rates):
            raise ProviderError("budget","invalid pricing")
        if any(isinstance(m.get("content"),list) for m in body["messages"]):
            raise ProviderError("budget","image token upper bound unavailable; image request needs separate validated budget policy")
        # Upper bound for ordinary text token input, including tool definitions.
        upper_input=len(canonical(body).encode())
        upper_output=body.get("max_tokens",body.get("max_completion_tokens",0))
        reserve=(upper_input*rates[0]+upper_output*rates[1])/1_000_000
        if used_cost+reserve>max_cost:
            raise ProviderError("budget","cost reserve exceeds configured limit")

    def complete(self, messages, tools=(), max_output_tokens=256, max_cost=None, used_cost=0.0, probe=False, budget_scope="default"):
        if max_cost is not None and self.store is not None:
            with self.store.coordinator_lock():
                return self._complete(messages,tools,max_output_tokens,max_cost,used_cost,probe,budget_scope)
        return self._complete(messages,tools,max_output_tokens,max_cost,used_cost,probe,budget_scope)

    def _complete(self, messages, tools=(), max_output_tokens=256, max_cost=None, used_cost=0.0, probe=False, budget_scope="default"):
        if max_output_tokens<=0:
            raise ValueError("positive output token bound required")
        config=self.config
        if tools and config["tool_calling"]!="verified" and not probe:
            raise ProviderError("capability","tool calling has not been verified for this configuration")
        if any(isinstance(m.get("content"),list) for m in messages) and config["vision"]!="verified" and not probe:
            raise ProviderError("capability","vision has not been verified")
        key=os.environ.get(config["api_key_env"])
        if not key:
            raise ProviderError("configuration","configured API key variable is not available")
        names={}
        native=[]
        for tool in tools:
            validate("tool",tool)
            Draft202012Validator.check_schema(tool["parameters"])
            name=tool["name"].replace(".","__")
            if name in names:
                raise ValueError("wire tool name collision")
            names[name]=tool
            native.append(dict(type="function",function=dict(name=name,description=tool["description"],parameters=tool["parameters"])))
        body=dict(model=config["model"],messages=messages,stream=False,**config["extra_body"])
        body["max_completion_tokens" if config["provider"]=="openai" else "max_tokens"]=max_output_tokens
        if native:
            body["tools"]=native
            body["tool_choice"]={"type":"function","function":{"name":native[0]["function"]["name"]}} if probe else "auto"
        if len(canonical(body).encode())+max_output_tokens>config["context_tokens"]:
            raise ProviderError("context","conservative text context bound exceeded")
        used_cost=self._spent(budget_scope,max_cost,used_cost)
        self._budget(body,max_cost,used_cost)
        start=time.monotonic()
        record=dict(model=config["model"],status="started",retry_count=0,usage=None,cost=None,pricing_source=(config["pricing"] or {}).get("source_url"),probe=probe,budget_scope=budget_scope)
        entry_id=self._record(record)
        # No automatic retries: even a lost model response may have incurred cost.
        try:
            response=self.client.post(config["base_url"].rstrip("/")+"/chat/completions",json=body,headers={"Authorization":"Bearer "+key})
        except httpx.TimeoutException:
            record.update(status="timeout",duration_seconds=time.monotonic()-start)
            self._record(record,entry_id)
            raise ProviderError("timeout","provider timeout; cost unknown, retry requires budget reconciliation") from None
        except httpx.HTTPError:
            record.update(status="network_error",duration_seconds=time.monotonic()-start)
            self._record(record,entry_id)
            raise ProviderError("network","provider connection failed; no automatic retry") from None
        record.update(http_status=response.status_code,duration_seconds=time.monotonic()-start)
        if response.status_code>=300:
            kind="authentication" if response.status_code in (401,403) else "rate_limit" if response.status_code==429 else "server" if response.status_code>=500 else "request"
            record["status"]=kind; self._record(record,entry_id)
            raise ProviderError(kind,f"provider HTTP {response.status_code}; response body omitted")
        try:
            result=strict_json(response.text)
            message=result["choices"][0]["message"]
            record["actual_model"]=result.get("model",config["model"])
            usage=result.get("usage")
            if usage:
                if not all(isinstance(usage.get(k),int) and not isinstance(usage.get(k),bool) and usage[k]>=0 for k in ("prompt_tokens","completion_tokens","total_tokens")):
                    raise ValueError("invalid usage counters")
                record["usage"]={k:usage[k] for k in ("prompt_tokens","completion_tokens","total_tokens") if k in usage}
                pricing=config["pricing"]
                if pricing and "prompt_tokens" in usage and "completion_tokens" in usage:
                    record["cost"]=(usage["prompt_tokens"]*pricing["input_per_million"]+usage["completion_tokens"]*pricing["output_per_million"])/1_000_000
                    record["currency"]=pricing["currency"]
            proposals=[]; call_ids=set()
            # Validate the entire batch before returning even the first proposal.
            if result["choices"][0].get("finish_reason") in ("length","content_filter"):
                raise ValueError("incomplete response")
            for call in message.get("tool_calls",[]) or []:
                if call["type"]!="function" or call["id"] in call_ids:
                    raise ValueError("invalid/duplicate tool call")
                call_ids.add(call["id"])
                tool=names[call["function"]["name"]]
                arguments=strict_json(call["function"]["arguments"])
                Draft202012Validator(tool["parameters"]).validate(arguments)
                proposals.append(dict(call_id=call["id"],tool=tool["name"],arguments=arguments))
            record["status"]="succeeded"; self._record(record,entry_id)
            return dict(content=message.get("content"),tool_proposals=proposals,usage=record,execution_authorized=False)
        except Exception:
            record["status"]="invalid_response"; self._record(record,entry_id)
            raise ProviderError("invalid_response","provider output failed parsing/schema validation; no proposals released") from None

    def probe(self):
        tool=dict(schema_revision=VERSION,name="probe.echo",version=VERSION,description="Echo the integer 7",side_effects=False,parameters={"type":"object","properties":{"value":{"type":"integer","const":7}},"required":["value"],"additionalProperties":False},implementation_kind="mock")
        result=self.complete([{"role":"user","content":"Call probe.echo with value 7."}],[tool],max_output_tokens=64,probe=True)
        ok=len(result["tool_proposals"])==1 and result["tool_proposals"][0]["arguments"]=={"value":7}
        return dict(provider=self.config["provider"],model=self.config["model"],tool_calling="verified" if ok else "unsupported",vision="unknown",observed_at=now(),usage=result["usage"],scope="this model, endpoint and configuration only")

    def probe_vision(self, image_path, expected):
        from pathlib import Path
        path=Path(image_path)
        mime="image/png" if path.suffix.lower()==".png" else "image/jpeg"
        encoded=base64.b64encode(path.read_bytes()).decode()
        result=self.complete([{"role":"user","content":[{"type":"text","text":"Describe the image in one short sentence."},{"type":"image_url","image_url":{"url":f"data:{mime};base64,{encoded}"}}]}],max_output_tokens=64,probe=True)
        text=result["content"] or ""
        return dict(vision="verified" if expected.casefold() in text.casefold() else "unknown",expected=expected,response=text,observed_at=now(),scope="single supplied probe; human review required")
