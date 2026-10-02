"""Publish commit-bound desktop previews; no third-party Python dependencies."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "Vivo50E/SiLing"


def api(method: str, path: str, data=None, *, upload: bool = False):
    """Only an explicit GET 404 means absence; auth/network failures fail closed."""
    token = os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("GH_TOKEN is required")
    host = "uploads.github.com" if upload else "api.github.com"
    payload = data if upload else (json.dumps(data).encode() if data is not None else None)
    request = Request(f"https://{host}/repos/{REPOSITORY}/{path}", data=payload,
                      method=method, headers={
                          "Authorization": f"Bearer {token}",
                          "Accept": "application/vnd.github+json",
                          "Content-Type": "application/octet-stream" if upload else "application/json",
                          "X-GitHub-Api-Version": "2022-11-28",
                      })
    try:
        with urlopen(request, timeout=120) as response:
            body = response.read()
            return json.loads(body) if body else None
    except HTTPError as exc:
        status = exc.code
        exc.close()
        if method == "GET" and status == 404:
            return None
        # Never include response bodies, headers or tokens in CI errors.
        raise RuntimeError(f"GitHub {method} failed (HTTP {status})") from None


def identity(sha: str, channel: str = "preview") -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Expected a full commit SHA")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if head != sha:
        raise ValueError("Checkout does not match the release commit")
    version = json.loads((ROOT / "apps/desktop/package.json").read_text())["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Expected a stable desktop base version")
    if channel not in ("preview", "sparkle"):
        raise ValueError("Invalid release channel")
    return f"desktop-v{version}-{channel}.{sha[:12]}"


def asset_names(tag: str) -> list[str]:
    names = [f"SiLing-{tag}-mac-{arch}.zip" for arch in ("arm64", "x64")]
    if "-sparkle." in tag:
        names += ["appcast-arm64.xml", "appcast-x64.xml"]
    return names + ["SHA256SUMS.txt"]


def existing_release(tag: str, sha: str):
    ref = api("GET", f"git/ref/tags/{quote(tag, safe='')}")
    if ref and (ref.get("object", {}).get("type") != "commit"
                or ref.get("object", {}).get("sha") != sha):
        raise ValueError("Existing release tag does not point directly to the expected commit")
    release = api("GET", f"releases/tags/{quote(tag, safe='')}")
    if release:
        if (release.get("tag_name") != tag or release.get("target_commitish") != sha
                or release.get("prerelease") is not ("-sparkle." not in tag)):
            raise ValueError("Existing release is not this commit's desktop preview")
        assets = release.get("assets", [])
        names = [asset["name"] for asset in assets]
        if len(names) != len(set(names)) or set(names) - set(asset_names(tag)):
            raise ValueError("Existing release contains unexpected assets")
        if not release["draft"] and (set(names) != set(asset_names(tag))
                                     or any(a.get("state") != "uploaded" for a in assets)):
            raise ValueError("Published preview is incomplete; maintainer review required")
    return release


def publish(tag: str, sha: str, directory: Path) -> None:
    names = asset_names(tag)
    archives = [directory / name for name in names if name.endswith(".zip")]
    if any(p.is_symlink() or not p.is_file() or not p.stat().st_size for p in archives):
        raise ValueError("Both verified architecture archives are required")
    sums = "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in archives)
    extra_assets = []
    online = "-sparkle." in tag
    if online:
        if subprocess.check_output(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT, text=True).strip() != "false":
            raise ValueError("Online releases require full Git history for monotonic build numbers")
        build = subprocess.check_output(["git", "rev-list", "--count", "HEAD"], cwd=ROOT, text=True).strip()
        for arch, archive in zip(("arm64", "x64"), archives):
            # The private key stays in the publish process environment; never log it.
            result = subprocess.run(["node", str(ROOT / "apps/desktop/sign-release.cjs"),
                                     str(archive), tag, arch, build], cwd=ROOT,
                                    capture_output=True, check=False, timeout=120)
            if result.returncode != 0:
                raise RuntimeError("Update signing failed; verify the release key matches the pinned public key")
            extra_assets.append((f"appcast-{arch}.xml", result.stdout))
    release = existing_release(tag, sha)
    if release and not release["draft"]:
        print("Preview already published; no assets changed.")
        return
    if not release:
        release = api("POST", "releases", {
            "tag_name": tag, "target_commitish": sha, "name": f"SiLing {tag}",
            "draft": True, "prerelease": not online, "make_latest": "false",
            "body": (
                f"SiLing online-update build / 在线更新客户端\n\nCommit: `{sha}`\n\n"
                "Install this client once. Future updates use Sparkle and Ed25519 signatures; "
                "no paid Apple account is required. These apps are ad-hoc signed, not notarized. "
                "macOS may require explicit approval for first launch. Dashboard and Agents are not restarted.\n\n"
                f"[Desktop guide](https://github.com/{REPOSITORY}/blob/{sha}/docs/desktop-browser.md)"
            ) if online else (
                f"Automated desktop preview / 自动桌面预览版\n\nCommit: `{sha}`\n\n"
                    "mac-arm64: Apple Silicon; mac-x64: Intel. Verify with "
                    "`shasum -a 256 -c SHA256SUMS.txt` after downloading both ZIPs.\n\n"
                    "Ad-hoc signed only, **not Apple-notarized**. Gatekeeper may block downloaded builds; "
                    "do not disable security checks. Build from source if needed.\n"
                    "仅临时签名，**未经 Apple 公证**；下载后可能被 macOS 阻止，请勿关闭安全检查。\n\n"
                    "Requires a separately running Dashboard. Manual app replacement only; "
                    "no server update, session restart or desktop auto-update.\n"
                    "需单独启动 Dashboard；此发布不会更新服务端或重启会话。\n\n"
                    f"[Desktop guide](https://github.com/{REPOSITORY}/blob/{sha}/docs/desktop-browser.md)"
            ),
        })
    release_id = release["id"]
    # Retry only this commit's unpublished draft. Published assets are immutable here.
    for asset in release.get("assets", []):
        api("DELETE", f"releases/assets/{asset['id']}")
    for name, payload in [(p.name, p) for p in archives] + extra_assets + [(names[-1], sums.encode())]:
        data = payload.read_bytes() if isinstance(payload, Path) else payload
        asset = api("POST", f"releases/{release_id}/assets?name={quote(name, safe='')}",
                    data, upload=True)
        if asset.get("state") != "uploaded" or asset.get("size") != len(data):
            raise RuntimeError("Release upload did not complete; leaving an unpublished draft")
    # This is deliberately last: failures leave a draft, never a partial public release.
    api("PATCH", f"releases/{release_id}", {"draft": False, "prerelease": not online, "make_latest": "true" if online else "false"})
    print(f"https://github.com/{REPOSITORY}/releases/tag/{tag}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "publish"))
    parser.add_argument("--sha", required=True)
    parser.add_argument("--channel", choices=("preview", "sparkle"), default="preview")
    parser.add_argument("--artifacts", type=Path, default=ROOT / "dist/release")
    args = parser.parse_args()
    tag = identity(args.sha, args.channel)
    if args.command == "plan":
        release = existing_release(tag, args.sha)
        print(f"tag={tag}")
        print(f"build={'true' if not release or release['draft'] else 'false'}")
    else:
        publish(tag, args.sha, args.artifacts)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Desktop release failed: {error}", file=sys.stderr)
        raise SystemExit(1)
