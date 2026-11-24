"""
NetSage AI - Rule Checker
Deterministic, regex/string-based checks over raw CLI command output.
Runs independently of the LLM. Used to (a) flag known error patterns
and (b) validate/ground the AI's diagnosis against hard evidence.
"""

import re
import json


def check_missing_nat_outside(command_outputs: dict) -> list:
    """Flags interfaces with NAT overload/static configured but missing 'ip nat outside'."""
    flags = []
    text = " ".join(str(v) for v in command_outputs.values())
    has_nat_inside_source = "ip nat inside source" in text
    has_nat_outside = "ip nat outside" in text
    if has_nat_inside_source and not has_nat_outside:
        flags.append({
            "rule": "missing_nat_outside",
            "message": "NAT translation configured ('ip nat inside source') but no interface has 'ip nat outside'."
        })
    return flags


def check_encapsulation_vlan_mismatch(command_outputs: dict) -> list:
    """Flags sub-interfaces where the interface name's VLAN number doesn't match its encapsulation dot1Q number."""
    flags = []
    text = " ".join(str(v) for v in command_outputs.values())
    # find patterns like "GigabitEthernet0/0.20 ... encapsulation dot1Q 10"
    pattern = re.compile(r"(\w+Ethernet\d+/\d+\.(\d+))[^!]*?encapsulation dot1[Qq]\s+(\d+)", re.DOTALL)
    for match in pattern.finditer(text):
        subif_vlan, encap_vlan = match.group(2), match.group(3)
        if subif_vlan != encap_vlan:
            flags.append({
                "rule": "encapsulation_vlan_mismatch",
                "message": f"Sub-interface .{subif_vlan} has mismatched encapsulation dot1Q {encap_vlan}."
            })
    return flags


def check_dhcp_service_disabled(command_outputs: dict) -> list:
    flags = []
    text = " ".join(str(v) for v in command_outputs.values())
    if "no service dhcp" in text:
        flags.append({
            "rule": "dhcp_service_disabled",
            "message": "'no service dhcp' found — DHCP service is globally disabled on this device."
        })
    return flags


def check_dhcp_pool_exhausted(command_outputs: dict) -> list:
    flags = []
    text = " ".join(str(v) for v in command_outputs.values())
    match = re.search(r"Total addresses:\s*(\d+).*?Leased addresses:\s*(\d+)", text, re.DOTALL)
    if match:
        total, leased = int(match.group(1)), int(match.group(2))
        if total > 0 and leased >= total:
            flags.append({
                "rule": "dhcp_pool_exhausted",
                "message": f"DHCP pool exhausted: {leased}/{total} addresses leased."
            })
    return flags


def check_missing_ip_helper(command_outputs: dict) -> list:
    flags = []
    text = " ".join(str(v) for v in command_outputs.values())
    if "dhcp" in text.lower() and "ip helper-address" not in text and "dhcp pool" not in text.lower():
        # subnet references DHCP need but no local pool and no helper — ambiguous signal, kept soft
        pass
    if "no ip helper-address configured" in text:
        flags.append({
            "rule": "missing_ip_helper",
            "message": "No 'ip helper-address' configured; DHCP requests won't be relayed to a remote server."
        })
    return flags


def check_missing_dns_server(command_outputs: dict) -> list:
    flags = []
    text = " ".join(str(v) for v in command_outputs.values())
    if "DNS Servers: 0.0.0.0" in text or "no dns-server line configured" in text:
        flags.append({
            "rule": "missing_dns_server",
            "message": "No DNS server address is being handed out to clients."
        })
    return flags


def check_missing_default_route(command_outputs: dict) -> list:
    flags = []
    text = " ".join(str(v) for v in command_outputs.values())
    if "gateway of last resort is not set" in text.lower() or "no default route" in text.lower():
        flags.append({
            "rule": "missing_default_route",
            "message": "No default route (0.0.0.0/0) configured — no path to unknown/external networks."
        })
    return flags


def check_acl_no_permit_all(command_outputs: dict) -> list:
    flags = []
    text = " ".join(str(v) for v in command_outputs.values())
    if "access list" in text.lower() and "deny" in text.lower() and "permit ip any any" not in text.lower() \
            and "permit any" not in text.lower():
        flags.append({
            "rule": "acl_missing_permit_all",
            "message": "ACL has deny statement(s) with no trailing permit — implicit deny-all may block unintended traffic."
        })
    return flags


def check_acl_not_applied(command_outputs: dict) -> list:
    flags = []
    text = " ".join(str(v) for v in command_outputs.values())
    if "access list" in text.lower() and "ip access-group" not in text.lower() \
            and "was never applied" not in text.lower():
        # Soft signal only when case text hints at "not applied"
        if "no 'ip access-group'" in text or "not present" in text.lower():
            flags.append({
                "rule": "acl_not_applied",
                "message": "ACL exists but is not applied to any interface with 'ip access-group'."
            })
    return flags


def check_same_wifi_channel(command_outputs: dict) -> list:
    flags = []
    channels = re.findall(r"Channel:\s*(\d+)", " ".join(str(v) for v in command_outputs.values()))
    if len(channels) > 1 and len(set(channels)) == 1:
        flags.append({
            "rule": "wifi_channel_overlap",
            "message": f"Multiple APs detected on the same channel ({channels[0]}) — co-channel interference likely."
        })
    return flags


def check_trunk_not_trunking(command_outputs: dict) -> list:
    flags = []
    text = " ".join(str(v) for v in command_outputs.values())
    if "not-trunking" in text:
        flags.append({
            "rule": "trunk_not_trunking",
            "message": "A link expected to trunk shows 'not-trunking' status — mode mismatch likely."
        })
    return flags


ALL_RULES = [
    check_missing_nat_outside,
    check_encapsulation_vlan_mismatch,
    check_dhcp_service_disabled,
    check_dhcp_pool_exhausted,
    check_missing_ip_helper,
    check_missing_dns_server,
    check_missing_default_route,
    check_acl_no_permit_all,
    check_acl_not_applied,
    check_same_wifi_channel,
    check_trunk_not_trunking,
]


def run_rule_checker(command_outputs: dict) -> list:
    """Runs all rule checks against a case's command_outputs dict. Returns a flat list of flags."""
    all_flags = []
    for rule_fn in ALL_RULES:
        all_flags.extend(rule_fn(command_outputs))
    return all_flags


def run_on_all_cases(cases_path: str = "data/cases.json") -> dict:
    """Runs the rule checker on every case in the dataset. Returns {case_id: [flags]}."""
    with open(cases_path) as f:
        cases = json.load(f)
    results = {}
    for case in cases:
        flags = run_rule_checker(case["command_outputs"])
        results[case["case_id"]] = flags
    return results


if __name__ == "__main__":
    results = run_on_all_cases("../data/cases.json")
    flagged = {k: v for k, v in results.items() if v}
    print(f"{len(flagged)} / {len(results)} cases triggered at least one rule flag\n")
    for case_id, flags in flagged.items():
        print(f"{case_id}:")
        for f in flags:
            print(f"  - [{f['rule']}] {f['message']}")
