from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_AMI_SSM_PARAMETER = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Phase 2 EC2 preflight for Gemma QLoRA training. "
            "Checks AWS identity, network/key inputs, AMI resolution, "
            "instance offerings, and EC2 quota signals."
        )
    )
    parser.add_argument("--profile", default="default")
    parser.add_argument("--region", default="us-east-2")
    parser.add_argument("--instance-type", default="g6e.xlarge")
    parser.add_argument("--subnet-id", required=True)
    parser.add_argument("--security-group-id", required=True)
    parser.add_argument("--key-name", required=True)
    parser.add_argument("--ami-ssm-parameter", default=DEFAULT_AMI_SSM_PARAMETER)
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("E:/AI/rComp/execution_plan_11_5/kg/reports/phase2_ec2_preflight_latest.json"),
    )
    return parser.parse_args()


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _result(name: str, status: str, detail: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "status": status, "detail": detail}


def _safe_error(exc: Exception) -> dict[str, str]:
    code = "Unknown"
    try:
        code = str(exc.response.get("Error", {}).get("Code", "Unknown"))  # type: ignore[attr-defined]
    except Exception:
        pass
    return {"type": exc.__class__.__name__, "code": code, "message": str(exc)}


def _pick_quota(quotas: list[dict[str, Any]], needle: str) -> dict[str, Any] | None:
    n = needle.lower()
    for quota in quotas:
        if n in str(quota.get("QuotaName", "")).lower():
            return quota
    return None


def run() -> int:
    args = parse_args()
    payload: dict[str, Any] = {
        "timestamp_utc": _utc_now(),
        "profile": args.profile,
        "region": args.region,
        "instance_type": args.instance_type,
        "inputs": {
            "subnet_id": args.subnet_id,
            "security_group_id": args.security_group_id,
            "key_name": args.key_name,
            "ami_ssm_parameter": args.ami_ssm_parameter,
        },
        "checks": [],
        "status": "unknown",
        "blocker_class": "unknown",
        "auth_status": "unknown",
        "quota_status": "unknown",
    }

    blocking = False

    try:
        import boto3
    except Exception as exc:
        payload["checks"].append(
            _result(
                "python_dependency_boto3",
                "fail",
                {"error": _safe_error(exc)},
            )
        )
        payload["status"] = "blocked"
        payload["blocker_class"] = "auth_or_dependency"
        args.report_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote preflight report: {args.report_path}")
        print("Preflight blocker: auth_or_dependency")
        return 2

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    sts = session.client("sts")
    ec2 = session.client("ec2")
    ssm = session.client("ssm")
    sq = session.client("service-quotas")

    try:
        ident = sts.get_caller_identity()
        payload["auth_status"] = "ok"
        payload["checks"].append(
            _result(
                "sts_identity",
                "pass",
                {
                    "account": ident.get("Account"),
                    "arn": ident.get("Arn"),
                    "user_id": ident.get("UserId"),
                },
            )
        )
    except Exception as exc:
        blocking = True
        payload["auth_status"] = "blocked"
        payload["blocker_class"] = "auth"
        payload["checks"].append(_result("sts_identity", "fail", {"error": _safe_error(exc)}))

    subnet_az = None
    try:
        subnet = ec2.describe_subnets(SubnetIds=[args.subnet_id])["Subnets"][0]
        subnet_az = str(subnet.get("AvailabilityZone"))
        payload["checks"].append(
            _result(
                "subnet",
                "pass",
                {
                    "subnet_id": args.subnet_id,
                    "availability_zone": subnet_az,
                    "vpc_id": subnet.get("VpcId"),
                },
            )
        )
    except Exception as exc:
        blocking = True
        payload["checks"].append(_result("subnet", "fail", {"error": _safe_error(exc)}))

    try:
        sg = ec2.describe_security_groups(GroupIds=[args.security_group_id])["SecurityGroups"][0]
        payload["checks"].append(
            _result(
                "security_group",
                "pass",
                {
                    "group_id": sg.get("GroupId"),
                    "group_name": sg.get("GroupName"),
                    "vpc_id": sg.get("VpcId"),
                },
            )
        )
    except Exception as exc:
        blocking = True
        payload["checks"].append(_result("security_group", "fail", {"error": _safe_error(exc)}))

    try:
        kp = ec2.describe_key_pairs(KeyNames=[args.key_name])["KeyPairs"][0]
        payload["checks"].append(
            _result(
                "key_pair",
                "pass",
                {
                    "key_name": kp.get("KeyName"),
                    "key_pair_id": kp.get("KeyPairId"),
                    "key_type": kp.get("KeyType"),
                },
            )
        )
    except Exception as exc:
        blocking = True
        payload["checks"].append(_result("key_pair", "fail", {"error": _safe_error(exc)}))

    try:
        param = ssm.get_parameter(Name=args.ami_ssm_parameter)
        ami_id = str(param.get("Parameter", {}).get("Value", ""))
        payload["resolved_ami_id"] = ami_id
        payload["checks"].append(
            _result("ami_ssm_resolution", "pass", {"parameter": args.ami_ssm_parameter, "ami_id": ami_id})
        )
    except Exception as exc:
        blocking = True
        payload["checks"].append(_result("ami_ssm_resolution", "fail", {"error": _safe_error(exc)}))

    try:
        filters = [{"Name": "instance-type", "Values": [args.instance_type]}]
        if subnet_az:
            filters.append({"Name": "location", "Values": [subnet_az]})
        offerings = ec2.describe_instance_type_offerings(
            LocationType="availability-zone",
            Filters=filters,
        ).get("InstanceTypeOfferings", [])
        status = "pass" if offerings else "warn"
        if not offerings:
            blocking = True
        payload["checks"].append(
            _result(
                "instance_offering_in_az",
                status,
                {
                    "instance_type": args.instance_type,
                    "availability_zone": subnet_az,
                    "offering_count": len(offerings),
                },
            )
        )
    except Exception as exc:
        payload["checks"].append(
            _result("instance_offering_in_az", "warn", {"error": _safe_error(exc)})
        )

    try:
        quota_pages = sq.get_paginator("list_service_quotas")
        quotas: list[dict[str, Any]] = []
        for page in quota_pages.paginate(ServiceCode="ec2"):
            quotas.extend(page.get("Quotas", []))

        ondemand_g_vt = _pick_quota(quotas, "Running On-Demand G and VT instances")
        spot_g_vt = _pick_quota(quotas, "All G and VT Spot Instance Requests")

        quota_detail = {
            "on_demand_g_vt": {
                "name": ondemand_g_vt.get("QuotaName") if ondemand_g_vt else None,
                "code": ondemand_g_vt.get("QuotaCode") if ondemand_g_vt else None,
                "value": ondemand_g_vt.get("Value") if ondemand_g_vt else None,
            },
            "spot_g_vt": {
                "name": spot_g_vt.get("QuotaName") if spot_g_vt else None,
                "code": spot_g_vt.get("QuotaCode") if spot_g_vt else None,
                "value": spot_g_vt.get("Value") if spot_g_vt else None,
            },
        }
        quota_status = "pass"
        if ondemand_g_vt and float(ondemand_g_vt.get("Value", 0.0)) <= 0.0:
            quota_status = "fail"
            blocking = True
            payload["quota_status"] = "blocked"
            payload["blocker_class"] = "quota"
        elif ondemand_g_vt:
            payload["quota_status"] = "ok"
        payload["checks"].append(_result("ec2_quota_signal", quota_status, quota_detail))
    except Exception as exc:
        payload["checks"].append(_result("ec2_quota_signal", "warn", {"error": _safe_error(exc)}))
        payload["quota_status"] = "not_checked"

    payload["status"] = "blocked" if blocking else "ready_for_launch_attempt"
    if payload["status"] == "blocked" and payload["blocker_class"] == "unknown":
        payload["blocker_class"] = "quota_or_external_capacity"
    if payload["status"] == "ready_for_launch_attempt" and payload["quota_status"] == "unknown":
        payload["quota_status"] = "not_checked"
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote preflight report: {args.report_path}")
    print(f"Preflight status: {payload['status']}")
    print(f"Preflight auth_status: {payload['auth_status']}")
    print(f"Preflight quota_status: {payload['quota_status']}")
    if payload["status"] == "blocked":
        if payload["blocker_class"] == "auth":
            print("Preflight blocker: auth")
        elif payload["blocker_class"] == "quota":
            print("Preflight blocker: quota")
        else:
            print("Preflight blocker: quota_or_external_capacity")
    return 2 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(run())
