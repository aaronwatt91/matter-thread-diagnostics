"""
Real Network, mDNS (_meshcop._udp, _matter._tcp, _matterc._udp), OTBR REST API,
IPv6 Routing (ULA/RIO), Neighbor Discovery, and Active ICMPv6 Ping Inspector.
"""
import asyncio
import ipaddress
import logging
import re
import socket
import struct
import time
from typing import Dict, Any, List, Optional
import httpx

logger = logging.getLogger("matter_thread_ai.network_checker")


def _decode_txt_bytes_or_hex(raw: Optional[bytes]) -> str:
    """Decode mDNS TXT value that may be raw binary bytes (8 or 16 bytes) or ASCII hex/text."""
    if not raw:
        return ""
    # Try UTF-8 printable string first if all bytes are printable ASCII
    if all(32 <= b <= 126 for b in raw):
        s = raw.decode("utf-8", errors="ignore").strip()
        return s
    # Otherwise convert binary bytes (e.g. 8-byte Extended PAN ID or Extended MAC) to uppercase hex
    return raw.hex().upper()


def _decode_ext_pan_or_mac(raw: Optional[bytes]) -> str:
    """Normalize 8-byte binary or 16-char ASCII hex TXT value into a 16-char uppercase hex string."""
    if not raw:
        return ""
    if len(raw) == 8:
        # Check if all 8 bytes happen to be hex chars or raw binary (8 raw bytes = 64-bit ID)
        return raw.hex().upper()
    if all(32 <= b <= 126 for b in raw):
        s = raw.decode("utf-8", errors="ignore").strip().replace(":", "").replace("-", "").upper()
        if s.startswith("0X"):
            s = s[2:]
        if all(c in "0123456789ABCDEF" for c in s):
            return s.zfill(16)
    return raw.hex().upper()


def _decode_state_bitmap(raw: Optional[bytes]) -> Dict[str, Any]:
    """Decode Thread MeshCoP State Bitmap ('sb' TXT key, 4-byte big-endian uint32)."""
    if not raw:
        return {}
    val = None
    if len(raw) == 4:
        val = struct.unpack(">I", raw)[0]
    elif all(48 <= b <= 57 for b in raw):
        try:
            val = int(raw.decode("ascii"))
        except ValueError:
            pass
    if val is None:
        return {}

    conn_mode = val & 0x07
    thread_if_status = (val >> 3) & 0x03
    availability = (val >> 5) & 0x03
    bbr_active = bool((val >> 7) & 0x01)
    bbr_primary = bool((val >> 8) & 0x01)

    if_status_map = {0: "Not Initialized", 1: "Detached", 2: "Attached (Active)"}
    return {
        "raw": val,
        "connection_mode": conn_mode,
        "thread_interface_status": if_status_map.get(thread_if_status, "Unknown"),
        "thread_attached": thread_if_status == 2,
        "availability": availability,
        "bbr_active": bbr_active,
        "bbr_primary": bbr_primary,
    }


class NetworkChecker:
    @staticmethod
    async def inspect_ipv6_routes() -> Dict[str, Any]:
        """
        Inspect kernel IPv6 routing table and Neighbor Discovery cache for Thread ULA
        prefixes (fd00::/8) advertised via ICMPv6 Route Information Options (RIO).
        Works on Linux (HAOS `ip -6 route show`) and macOS (`netstat -rn -f inet6`).
        """
        routes: List[str] = []
        ula_routes_detailed: List[Dict[str, str]] = []
        thread_ula_prefixes: List[str] = []
        neighbors: List[Dict[str, str]] = []
        has_thread_ula_route = False

        # 1. Query IPv6 routing table via `ip -6 route show`
        try:
            proc = await asyncio.create_subprocess_exec(
                "ip", "-6", "route", "show",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                for line in stdout.decode(errors="ignore").splitlines():
                    line_clean = line.strip()
                    if not line_clean:
                        continue
                    routes.append(line_clean)
                    if line_clean.lower().startswith("fd"):
                        has_thread_ula_route = True
                        prefix_match = re.match(r"^(fd[0-9a-f:]+/\d+)", line_clean.lower())
                        via_match = re.search(r"via\s+([0-9a-f:]+)", line_clean.lower())
                        dev_match = re.search(r"dev\s+(\S+)", line_clean)
                        proto_match = re.search(r"proto\s+(\S+)", line_clean)
                        prefix = prefix_match.group(1) if prefix_match else line_clean.split()[0]
                        if prefix not in thread_ula_prefixes:
                            thread_ula_prefixes.append(prefix)
                        ula_routes_detailed.append({
                            "prefix": prefix,
                            "via": via_match.group(1) if via_match else "direct/on-link",
                            "interface": dev_match.group(1) if dev_match else "unknown",
                            "protocol": proto_match.group(1) if proto_match else "kernel",
                            "raw": line_clean,
                        })
        except FileNotFoundError:
            # Fallback for macOS (`netstat -rn -f inet6`)
            try:
                proc = await asyncio.create_subprocess_exec(
                    "netstat", "-rn", "-f", "inet6",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                if proc.returncode == 0:
                    for line in stdout.decode(errors="ignore").splitlines():
                        line_clean = line.strip()
                        if not line_clean or line_clean.startswith("Routing") or line_clean.startswith("Internet6"):
                            continue
                        routes.append(line_clean)
                        if line_clean.lower().startswith("fd"):
                            parts = line_clean.split()
                            prefix = parts[0]
                            gw = parts[1] if len(parts) > 1 else ""
                            iface = parts[3] if len(parts) > 3 else ""
                            # Ignore loopback ULA entries if any
                            if "lo0" not in iface:
                                has_thread_ula_route = True
                                if prefix not in thread_ula_prefixes:
                                    thread_ula_prefixes.append(prefix)
                                ula_routes_detailed.append({
                                    "prefix": prefix,
                                    "via": gw,
                                    "interface": iface,
                                    "protocol": "ra",
                                    "raw": line_clean,
                                })
            except Exception as e:
                logger.debug("Fallback netstat failed: %s", e)
        except Exception as e:
            logger.warning("Failed running 'ip -6 route show': %s", e)
            routes = [f"Error querying IPv6 routes: {e}"]

        # 2. Query IPv6 Neighbor Discovery cache (`ip -6 neigh show`)
        try:
            proc_n = await asyncio.create_subprocess_exec(
                "ip", "-6", "neigh", "show",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_n, _ = await proc_n.communicate()
            if proc_n.returncode == 0:
                for line in stdout_n.decode(errors="ignore").splitlines():
                    line_clean = line.strip()
                    if not line_clean:
                        continue
                    parts = line_clean.split()
                    ip_addr = parts[0] if parts else ""
                    state = parts[-1] if parts else ""
                    lladdr_m = re.search(r"lladdr\s+([0-9a-f:]+)", line_clean.lower())
                    dev_m = re.search(r"dev\s+(\S+)", line_clean)
                    neighbors.append({
                        "ipv6": ip_addr,
                        "mac": lladdr_m.group(1).upper() if lladdr_m else "",
                        "interface": dev_m.group(1) if dev_m else "",
                        "state": state,
                    })
        except Exception:
            pass

        return {
            "has_thread_ula_route": has_thread_ula_route,
            "detected_ula_prefixes": thread_ula_prefixes,
            "ula_routes_detailed": ula_routes_detailed,
            "neighbors_count": len(neighbors),
            "neighbors": neighbors[:25],
            "routes_count": len(routes),
            "sample_routes": routes[:20],
            "status": "PASS" if has_thread_ula_route else "WARNING",
            "summary": (
                f"Active IPv6 routes to Thread ULA prefix(es) detected: {', '.join(thread_ula_prefixes)}"
                if has_thread_ula_route
                else "WARNING: No IPv6 route to any Thread ULA prefix (fd00::/8) found in kernel routing table! "
                     "Ensure your Border Routers are powered on and IPv6 Router Advertisements (ICMPv6 RIO) are not blocked by your switch/Wi-Fi router."
            ),
        }

    @staticmethod
    async def inspect_mdns_discovery(scan_duration: float = 2.5) -> Dict[str, Any]:
        """
        Perform a REAL live mDNS scan on the local network using Python `zeroconf`
        (with `avahi-browse` fallback) for:
          - `_meshcop._udp.local.` (Thread Border Routers)
          - `_matter._tcp.local.` (Commissioned Operational Matter Nodes)
          - `_matterc._udp.local.` (Matter Commissioning Advertisements)
        """
        meshcop_routers: List[Dict[str, Any]] = []
        matter_operational_nodes: List[Dict[str, Any]] = []
        matter_commissionable_nodes: List[Dict[str, Any]] = []
        scanner_backend = "none"
        error_msg = None

        try:
            from zeroconf import ServiceStateChange, Zeroconf
            from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

            scanner_backend = "zeroconf"
            discovered_targets: List[tuple] = []

            def on_service_state_change(zeroconf: Zeroconf, service_type: str, name: str, state_change: ServiceStateChange) -> None:
                if state_change is ServiceStateChange.Added:
                    discovered_targets.append((service_type, name))

            azc = AsyncZeroconf()
            services = ["_meshcop._udp.local.", "_matter._tcp.local.", "_matterc._udp.local."]
            browser = AsyncServiceBrowser(azc.zeroconf, services, handlers=[on_service_state_change])

            await asyncio.sleep(scan_duration)

            # Resolve all discovered services concurrently
            async def resolve_one(svc_type: str, svc_name: str):
                info = AsyncServiceInfo(svc_type, svc_name)
                await info.async_request(azc.zeroconf, 2000)
                return svc_type, svc_name, info

            resolved = await asyncio.gather(
                *[resolve_one(st, sn) for st, sn in discovered_targets],
                return_exceptions=True,
            )

            for item in resolved:
                if isinstance(item, Exception) or not item:
                    continue
                svc_type, svc_name, info = item
                if not info:
                    continue

                # Extract IPv4 and IPv6 addresses
                all_ips = info.parsed_scoped_addresses() if hasattr(info, "parsed_scoped_addresses") else []
                ipv6_addrs = [ip for ip in all_ips if ":" in ip]
                ipv4_addrs = [ip for ip in all_ips if "." in ip]
                props: Dict[bytes, Optional[bytes]] = info.properties or {}

                instance_label = svc_name.replace(f".{svc_type}", "")

                if svc_type == "_meshcop._udp.local.":
                    nn = _decode_txt_bytes_or_hex(props.get(b"nn"))
                    xp = _decode_ext_pan_or_mac(props.get(b"xp"))
                    vn = _decode_txt_bytes_or_hex(props.get(b"vn"))
                    mn = _decode_txt_bytes_or_hex(props.get(b"mn"))
                    tv = _decode_txt_bytes_or_hex(props.get(b"tv"))
                    xa = _decode_ext_pan_or_mac(props.get(b"xa"))
                    ba = _decode_ext_pan_or_hex_len(props.get(b"ba"))
                    dn = _decode_txt_bytes_or_hex(props.get(b"dn"))
                    sb_info = _decode_state_bitmap(props.get(b"sb"))

                    meshcop_routers.append({
                        "instance_name": instance_label,
                        "service_name": svc_name,
                        "server": (info.server or "").rstrip("."),
                        "port": info.port,
                        "network_name": nn or instance_label,
                        "extended_pan_id": xp or "UNKNOWN",
                        "vendor_name": vn,
                        "model_name": mn,
                        "thread_version": tv,
                        "ext_address": xa,
                        "border_agent_id": ba,
                        "domain_name": dn,
                        "state_bitmap": sb_info,
                        "ipv6_addresses": ipv6_addrs,
                        "ipv4_addresses": ipv4_addrs,
                        "addresses": ipv6_addrs + ipv4_addrs,
                        "source": "mDNS (_meshcop._udp)",
                    })

                elif svc_type == "_matter._tcp.local.":
                    # Operational Matter service name format: <CompressedFabricId>-<NodeId>._matter._tcp.local.
                    fabric_part = ""
                    node_id_int = None
                    if "-" in instance_label:
                        parts = instance_label.split("-")
                        fabric_part = parts[0]
                        try:
                            node_id_int = int(parts[1], 16)
                        except ValueError:
                            pass

                    sii = _decode_txt_bytes_or_hex(props.get(b"SII"))
                    sai = _decode_txt_bytes_or_hex(props.get(b"SAI"))
                    matter_operational_nodes.append({
                        "instance_name": instance_label,
                        "compressed_fabric_id": fabric_part,
                        "node_id": node_id_int,
                        "node_id_hex": instance_label.split("-")[1] if "-" in instance_label else instance_label,
                        "server": (info.server or "").rstrip("."),
                        "port": info.port,
                        "ipv6_addresses": ipv6_addrs,
                        "ipv4_addresses": ipv4_addrs,
                        "session_idle_interval_ms": int(sii) if sii.isdigit() else None,
                        "session_active_interval_ms": int(sai) if sai.isdigit() else None,
                    })

                elif svc_type == "_matterc._udp.local.":
                    vp = _decode_txt_bytes_or_hex(props.get(b"VP"))
                    disc = _decode_txt_bytes_or_hex(props.get(b"D"))
                    cm = _decode_txt_bytes_or_hex(props.get(b"CM"))
                    matter_commissionable_nodes.append({
                        "instance_name": instance_label,
                        "server": (info.server or "").rstrip("."),
                        "port": info.port,
                        "vendor_product": vp,
                        "discriminator": disc,
                        "commissioning_mode": cm,
                        "ipv6_addresses": ipv6_addrs,
                        "ipv4_addresses": ipv4_addrs,
                    })

            await browser.async_cancel()
            await azc.async_close()

        except Exception as e:
            error_msg = str(e)
            logger.debug("Zeroconf mDNS scan encountered error (%s), trying avahi-browse fallback", e)
            # Fallback to `avahi-browse -rpt -k _meshcop._udp` if available
            try:
                proc = await asyncio.create_subprocess_exec(
                    "avahi-browse", "-rpt", "-k", "_meshcop._udp",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=4.0)
                if proc.returncode == 0:
                    scanner_backend = "avahi-browse"
                    for line in stdout.decode(errors="ignore").splitlines():
                        if not line.startswith("="):
                            continue
                        cols = line.split(";")
                        if len(cols) >= 10:
                            inst = cols[3]
                            host = cols[6]
                            addr = cols[7]
                            port = cols[8]
                            txt = cols[9]
                            nn_m = re.search(r'"nn=([^"]+)"', txt)
                            vn_m = re.search(r'"vn=([^"]+)"', txt)
                            mn_m = re.search(r'"mn=([^"]+)"', txt)
                            xp_m = re.search(r'"xp=([^"]+)"', txt)
                            meshcop_routers.append({
                                "instance_name": inst,
                                "server": host,
                                "port": int(port) if port.isdigit() else 0,
                                "network_name": nn_m.group(1) if nn_m else inst,
                                "extended_pan_id": xp_m.group(1).encode().hex().upper() if xp_m else "UNKNOWN",
                                "vendor_name": vn_m.group(1) if vn_m else "",
                                "model_name": mn_m.group(1) if mn_m else "",
                                "ipv6_addresses": [addr] if ":" in addr else [],
                                "ipv4_addresses": [addr] if "." in addr else [],
                                "addresses": [addr] if addr else [],
                                "source": "avahi-browse (_meshcop._udp)",
                            })
            except Exception:
                pass

        return {
            "mdns_capable": scanner_backend != "none",
            "scanner_backend": scanner_backend,
            "meshcop_border_routers_count": len(meshcop_routers),
            "meshcop_border_routers": meshcop_routers,
            "matter_operational_nodes_count": len(matter_operational_nodes),
            "matter_operational_nodes": matter_operational_nodes,
            "matter_commissionable_nodes_count": len(matter_commissionable_nodes),
            "matter_commissionable_nodes": matter_commissionable_nodes,
            "error": error_msg,
        }

    @staticmethod
    async def inspect_otbr_rest_api(otbr_url: str = "http://core-openthread-border-router:8081") -> Dict[str, Any]:
        """
        Query the OpenThread Border Router (OTBR) REST API (:8081) for live Thread node state,
        active operational dataset, RLOC16, Extended Address, Channel, Extended PAN ID, and Leader Data.
        """
        candidates = []
        if otbr_url:
            candidates.append(otbr_url.rstrip("/"))
        for fb in [
            "http://core-openthread-border-router:8081",
            "http://localhost:8081",
            "http://127.0.0.1:8081",
        ]:
            if fb not in candidates:
                candidates.append(fb)

        async with httpx.AsyncClient(timeout=2.5) as client:
            for base_url in candidates:
                try:
                    r_state = await client.get(f"{base_url}/node/state")
                    if r_state.status_code != 200:
                        continue

                    state_val = r_state.json() if "application/json" in r_state.headers.get("content-type", "") else r_state.text.strip().strip('"')

                    # Fetch additional OTBR endpoints concurrently
                    endpoints = {
                        "network_name": "/node/network-name",
                        "ext_panid": "/node/ext-panid",
                        "ext_address": "/node/ext-address",
                        "rloc16": "/node/rloc16",
                        "leader_data": "/node/leader-data",
                        "dataset_active": "/node/dataset/active",
                    }

                    async def fetch_ep(key: str, path: str):
                        try:
                            resp = await client.get(f"{base_url}{path}", headers={"Accept": "application/json"})
                            if resp.status_code == 200:
                                try:
                                    return key, resp.json()
                                except Exception:
                                    return key, resp.text.strip().strip('"')
                        except Exception:
                            pass
                        return key, None

                    ep_results = dict(await asyncio.gather(*[fetch_ep(k, p) for k, p in endpoints.items()]))

                    active_ds = ep_results.get("dataset_active")
                    channel = None
                    pan_id = None
                    mesh_local_prefix = None
                    if isinstance(active_ds, dict):
                        channel = active_ds.get("Channel") or active_ds.get("channel")
                        pan_id = active_ds.get("PanId") or active_ds.get("pan_id")
                        mesh_local_prefix = active_ds.get("MeshLocalPrefix") or active_ds.get("mesh_local_prefix")

                    xpan = str(ep_results.get("ext_panid") or "").upper().replace(":", "").replace("0X", "")
                    ext_addr = str(ep_results.get("ext_address") or "").upper().replace(":", "").replace("0X", "")
                    rloc_raw = ep_results.get("rloc16")
                    rloc_hex = f"0x{int(rloc_raw):04X}" if isinstance(rloc_raw, int) else (f"0x{str(rloc_raw).upper()}" if rloc_raw else None)

                    return {
                        "reachable": True,
                        "otbr_url": base_url,
                        "state": state_val,
                        "network_name": ep_results.get("network_name") or "OpenThread Mesh",
                        "extended_pan_id": xpan,
                        "ext_address": ext_addr,
                        "rloc16": rloc_hex,
                        "channel": channel,
                        "pan_id": f"0x{int(pan_id):04X}" if isinstance(pan_id, int) else pan_id,
                        "mesh_local_prefix": mesh_local_prefix,
                        "leader_data": ep_results.get("leader_data"),
                        "active_dataset": active_ds,
                    }
                except Exception:
                    continue

        return {"reachable": False, "otbr_url": otbr_url, "state": "unreachable"}

    @staticmethod
    async def ping_address(ip_addr: str, count: int = 2, timeout_sec: int = 1) -> Dict[str, Any]:
        """
        Execute a real ICMP/ICMPv6 ping against a target IPv6 or IPv4 address
        and return reachability, packet loss %, and round-trip latency (ms).
        """
        if not ip_addr:
            return {"ip": ip_addr, "reachable": False, "error": "Empty address"}

        # Strip zone index if not link-local, or preserve if fe80::
        clean_ip = ip_addr.split("/")[0].strip()
        is_ipv6 = ":" in clean_ip

        # Choose command arguments compatible with Linux iputils-ping and macOS ping6
        cmd = ["ping", "-6", "-c", str(count), "-W", str(timeout_sec), clean_ip] if is_ipv6 else ["ping", "-c", str(count), "-W", str(timeout_sec), clean_ip]

        t0 = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=count * timeout_sec + 2.0)
            except asyncio.TimeoutError:
                proc.kill()
                return {"ip": clean_ip, "reachable": False, "packet_loss_pct": 100.0, "rtt_ms": None, "error": "Ping timeout"}

            output = stdout.decode(errors="ignore") + "\n" + stderr.decode(errors="ignore")
            reachable = proc.returncode == 0

            # Parse packet loss
            loss_pct = 0.0 if reachable else 100.0
            loss_m = re.search(r"(\d+(?:\.\d+)?)%\s*packet loss", output)
            if loss_m:
                loss_pct = float(loss_m.group(1))

            # Parse average RTT (Linux: rtt min/avg/max/mdev = 1.123/2.345/3.456/0.123 ms; macOS: round-trip min/avg/max/stddev = ...)
            avg_rtt = None
            rtt_m = re.search(r"(?:rtt|round-trip)\s+min/avg/max/[a-z]+\s*=\s*[\d.]+/([\d.]+)/", output)
            if rtt_m:
                avg_rtt = round(float(rtt_m.group(1)), 2)
            elif reachable:
                avg_rtt = round((time.monotonic() - t0) * 1000.0 / max(count, 1), 2)

            return {
                "ip": clean_ip,
                "is_ipv6": is_ipv6,
                "reachable": reachable,
                "packet_loss_pct": loss_pct,
                "rtt_ms": avg_rtt,
            }
        except Exception as e:
            return {"ip": clean_ip, "is_ipv6": is_ipv6, "reachable": False, "packet_loss_pct": 100.0, "rtt_ms": None, "error": str(e)}

    @classmethod
    async def probe_network_reachability(cls, border_routers: List[Dict[str, Any]], matter_nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Actively ping discovered Border Routers and Matter-over-Thread nodes via ICMPv6/ICMPv4
        to verify real end-to-end packet routing from Home Assistant.
        """
        tasks = []
        target_meta = []

        # 1. Select best pingable address for each Border Router (prefer global/ULA IPv6 or IPv4 over scoped link-local without interface)
        for br in border_routers[:8]:
            addrs = br.get("addresses") or (br.get("ipv6_addresses", []) + br.get("ipv4_addresses", []))
            chosen = None
            for a in addrs:
                if ":" in a and not a.lower().startswith("fe80"):
                    chosen = a
                    break
                elif "." in a and not chosen:
                    chosen = a
                elif ":" in a and "%" in a and not chosen:
                    chosen = a
            if chosen:
                target_meta.append({"kind": "border_router", "name": br.get("name") or br.get("instance_name") or "Border Router", "ip": chosen})
                tasks.append(cls.ping_address(chosen, count=2, timeout_sec=1))

        # 2. Select Thread ULA (`fd...`) IPv6 address for each Matter node
        for node in matter_nodes[:12]:
            v6_list = node.get("ipv6_addresses") or []
            ula_ip = next((ip for ip in v6_list if ip.lower().startswith("fd")), None)
            target_ip = ula_ip or next((ip for ip in v6_list if not ip.lower().startswith("fe80")), None)
            if target_ip:
                target_meta.append({
                    "kind": "matter_node",
                    "node_id": node.get("node_id"),
                    "name": node.get("product_name") or f"Node {node.get('node_id')}",
                    "ip": target_ip,
                })
                tasks.append(cls.ping_address(target_ip, count=2, timeout_sec=1))

        if not tasks:
            return {"probed_count": 0, "reachable_count": 0, "results": []}

        ping_outputs = await asyncio.gather(*tasks, return_exceptions=True)
        results = []
        reachable_count = 0
        for meta, out in zip(target_meta, ping_outputs):
            if isinstance(out, Exception):
                entry = {**meta, "reachable": False, "rtt_ms": None, "packet_loss_pct": 100.0, "error": str(out)}
            else:
                entry = {**meta, **out}
                if entry.get("reachable"):
                    reachable_count += 1
            results.append(entry)

        return {
            "probed_count": len(results),
            "reachable_count": reachable_count,
            "results": results,
        }


def _decode_ext_pan_or_hex_len(raw: Optional[bytes]) -> str:
    if not raw:
        return ""
    return raw.hex().upper()
