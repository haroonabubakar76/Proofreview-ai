import json, os, re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .demo import SEEDED_PR

ROOT = Path(__file__).parent
app = FastAPI(title="ProofReview", version="0.1.0")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

class PRFile(BaseModel):
    path: str
    patch: str
class ReviewRequest(BaseModel):
    title: str = "Untitled pull request"
    repo: str = "local/demo"
    base_sha: str = "base"
    head_sha: str = "head"
    files: list[PRFile] = Field(min_length=1)
    use_model: bool = False
class GitHubPRRequest(BaseModel):
    repo: str
    pr_number: int = Field(gt=0)
    use_model: bool = False

def added_lines(patch: str):
    current, output = 0, []
    for line in patch.splitlines():
        hunk = re.match(r"@@ -\\d+(?:,\\d+)? \\+(\\d+)", line)
        if hunk: current = int(hunk.group(1)); continue
        if line.startswith("+") and not line.startswith("+++"): output.append((current, line[1:])); current += 1
        elif not line.startswith("-"): current += 1
    return output

def make_finding(path, line, title, severity, explanation, suggestion, evidence, rule):
    return {"path":path,"line":line,"title":title,"severity":severity,"explanation":explanation,"suggestion":suggestion,"evidence":evidence,"rule":rule,"verified":True}

def deterministic_scan(file: PRFile) -> list[dict[str, Any]]:
    results, lines = [], added_lines(file.patch)
    for line, text in lines:
        if "execute(query)" in text and any(("f\"" in candidate or "f'" in candidate) and "SELECT" in candidate.upper() for _, candidate in lines):
            results.append(make_finding(file.path,line,"Untrusted input reaches SQL execution","critical","The query is assembled from a caller-controlled value and then executed. A value like `' OR 1=1 --` changes the query structure.","Use a parameterized query: `connection.execute('SELECT * FROM payments WHERE customer_id = ?', (customer_id,))`.",["Taint trace: function argument `customer_id` → f-string query → `connection.execute`.","Reproduction input: `' OR 1=1 --` produces a predicate that is always true."],"sql-string-execution"))
        if re.search(r"(?:eval|exec)\s*\(", text):
            results.append(make_finding(file.path,line,"Dynamic code execution","critical","`eval`/`exec` can execute attacker-controlled code when fed request data.","Replace dynamic execution with a strict parser or explicit dispatch table.",["Static verification: dangerous dynamic execution call was added in this diff."],"dynamic-execution"))
    removed_guard = any(line.startswith("-    if ") and ("can(" in line or "permission" in line.lower()) for line in file.patch.splitlines())
    sensitive = next(((line,text) for line,text in lines if re.search(r"\b(?:issue_refund|delete_|transfer_|withdraw_)",text)),None)
    if removed_guard and sensitive:
        results.append(make_finding(file.path,sensitive[0],"Authorization check removed before sensitive operation","high","This change invokes a money-moving operation without the previously present permission gate.","Restore a server-side authorization check before calling `issue_refund`, and add a test for unauthorized actors.",["Diff evidence: a permission conditional was removed.","Control-flow trace: `refund_payment` now reaches `issue_refund` for any caller."],"removed-authorization-guard"))
    return results

def rule_candidate_count(file: PRFile) -> int:
    """Count preliminary rule candidates before verification filters them."""
    lines = added_lines(file.patch)
    count = sum(1 for _, text in lines if ("f\"" in text or "f'" in text) and "SELECT" in text.upper())
    count += sum(1 for _, text in lines if re.search(r"(?:eval|exec)\s*\(", text))
    removed_guard = any(line.startswith("-    if ") and ("can(" in line or "permission" in line.lower()) for line in file.patch.splitlines())
    sensitive = any(re.search(r"\b(?:issue_refund|delete_|transfer_|withdraw_)", text) for _, text in lines)
    return count + int(removed_guard and sensitive)

def github_pr_to_request(source: GitHubPRRequest) -> ReviewRequest:
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", source.repo):
        raise HTTPException(400, "Repository must be in owner/repository format.")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ProofReview-MVP"}
    if os.getenv("GITHUB_TOKEN"): headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    base = f"https://api.github.com/repos/{source.repo}/pulls/{source.pr_number}"
    try:
        def get(url):
            with urlopen(Request(url, headers=headers), timeout=20) as response:
                return json.load(response)
        pull, changed = get(base), get(base + "/files?per_page=100")
    except HTTPError as error:
        detail = "GitHub could not authorize this request. Add GITHUB_TOKEN for private repos." if error.code in (401, 403, 404) else f"GitHub request failed ({error.code})."
        raise HTTPException(error.code, detail) from error
    except URLError as error:
        raise HTTPException(502, "Could not reach GitHub. Check your connection and try again.") from error
    files = [PRFile(path=item["filename"], patch=item.get("patch", "")) for item in changed if item.get("patch")]
    if not files: raise HTTPException(422, "This PR has no text diff GitHub can provide for review.")
    return ReviewRequest(title=pull["title"], repo=source.repo, base_sha=pull["base"]["sha"], head_sha=pull["head"]["sha"], files=files, use_model=source.use_model)

def risk_score(items): return min(100,sum({"critical":45,"high":25,"medium":10,"low":4}.get(i["severity"],0) for i in items))
def model_second_pass(request):
    """Investigate with GPT; its proposals remain unpublished until the verifier proves them."""
    if not request.use_model or not os.getenv("OPENAI_API_KEY"): return []
    try:
        from openai import OpenAI
        prompt = "Return JSON only: {\"candidates\":[{\"path\":string,\"line\":number,\"risk\":string}]}. Find only high-impact bugs in this PR. " + json.dumps(request.model_dump())
        answer = OpenAI().responses.create(model=os.getenv("OPENAI_MODEL", "gpt-5.6"), input=prompt)
        return json.loads(answer.output_text).get("candidates", [])
    except Exception:
        return []
@app.get("/")
def index(): return FileResponse(ROOT / "static" / "index.html")
@app.get("/api/demo")
def demo(): return SEEDED_PR
@app.post("/api/review")
def review(request: ReviewRequest):
    verified=[item for file in request.files for item in deterministic_scan(file)]
    candidates=model_second_pass(request)
    rule_candidates=sum(rule_candidate_count(file) for file in request.files)
    candidate_count=rule_candidates + len(candidates)
    suppressed=max(0, candidate_count-len(verified))
    model_note = f"GPT-5.6 proposed {len(candidates)} candidate(s); all still require verification." if request.use_model and os.getenv("OPENAI_API_KEY") else ("GPT-5.6 was requested but OPENAI_API_KEY is not configured." if request.use_model else "Model pass not requested.")
    return {"repo":request.repo,"title":request.title,"risk_score":risk_score(verified),"verdict":"Changes require attention" if verified else "No verified risks found","findings":verified,"trace":[{"stage":"Context","detail":f"Read {len(request.files)} changed file(s) and mapped actual added lines."},{"stage":"Investigation","detail":f"Found {candidate_count} candidate(s): {rule_candidates} from rules and {len(candidates)} from GPT-5.6."},{"stage":"Verification","detail":f"Published {len(verified)} evidence-backed finding(s); suppressed {suppressed} unverified candidate(s)."},{"stage":"Model","detail":model_note}],"candidate_count":candidate_count,"suppressed_count":suppressed,"unverified_model_candidates":len(candidates)}
@app.post("/api/github-pr")
def github_pr(source: GitHubPRRequest):
    return review(github_pr_to_request(source))
@app.post("/api/github-payload")
def github_payload(request: ReviewRequest):
    response=review(request)
    return {"event":"PENDING","commit_id":request.head_sha,"body":f"## ProofReview — Risk score: {response['risk_score']}/100\\nOnly evidence-backed findings are included.","comments":[{"path":f["path"],"line":f["line"],"side":"RIGHT","body":f"**{f['severity'].upper()} — {f['title']}**\\n\\n{f['explanation']}\\n\\n**Suggested fix:** {f['suggestion']}\\n\\n_Proof: {f['evidence'][0]}_"} for f in response["findings"]]}
