#!/usr/bin/env python3
"""LAPTOP. Layer 7 (D46): the CloudFront Free plan attaches a web ACL whose AWS managed
rule groups are in Count mode (they record, they don't block). This turns every managed
group to Block and adds a per-IP rate limit (300 requests per 5 minutes), keeping every
other setting of the web ACL. The ACL belongs to the plan, not to Terraform.
  python3 scripts/waf-enforce.py          shows what it would set
  python3 scripts/waf-enforce.py apply    applies it
"""
import json
import subprocess
import sys


def aws(*args):
    out = subprocess.run(["aws", "wafv2", *args, "--scope", "CLOUDFRONT", "--region", "us-east-1",
                          "--no-cli-pager", "--output", "json"], capture_output=True, text=True, check=True).stdout
    return json.loads(out or "{}")


acl = next(a for a in aws("list-web-acls")["WebACLs"] if a["Name"].startswith("CreatedByCloudFront"))
got = aws("get-web-acl", "--name", acl["Name"], "--id", acl["Id"])
w = got["WebACL"]
rules = w["Rules"]
for r in rules:
    if "OverrideAction" in r:
        r["OverrideAction"] = {"None": {}}  # the managed group's own actions: block
if not any(r["Name"] == "RateLimitPerIP" for r in rules):
    rules.append({"Name": "RateLimitPerIP", "Priority": max(r["Priority"] for r in rules) + 1, "Action": {"Block": {}},
                  "Statement": {"RateBasedStatement": {"Limit": 300, "EvaluationWindowSec": 300, "AggregateKeyType": "IP"}},
                  "VisibilityConfig": {"SampledRequestsEnabled": True, "CloudWatchMetricsEnabled": True,
                                       "MetricName": "RateLimitPerIP"}})
keep = ("Name", "Id", "DefaultAction", "Description", "VisibilityConfig", "CustomResponseBodies", "CaptchaConfig",
        "ChallengeConfig", "TokenDomains", "AssociationConfig", "DataProtectionConfig")
body = {k: w[k] for k in keep if k in w and w[k] not in ("", None, [], {})}  # the API refuses empty values
body.update({"Scope": "CLOUDFRONT", "Rules": rules, "LockToken": got["LockToken"]})
for r in rules:
    blocks = r.get("OverrideAction") == {"None": {}} or "Block" in r.get("Action", {})
    print(f"{r['Priority']}  {r['Name']:<45} {'BLOCK' if blocks else r}")
if sys.argv[-1] == "apply":
    subprocess.run(["aws", "wafv2", "update-web-acl", "--region", "us-east-1", "--no-cli-pager",
                    "--cli-input-json", json.dumps(body)], check=True)
    print("applied")
