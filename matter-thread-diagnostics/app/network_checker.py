"""
Real Network, mDNS (_meshcop._udp, _matter._tcp, _matterc._udp), OTBR REST API,
IPv6 Routing (ULA/RIO), Neighbor Discovery, and Active ICMPv6 Ping Inspector.
Includes a zero-dependency pure-Python UDP DNS-SD mDNS scanner + AsyncZeroconf + avahi-browse.
"""
import asyncio
import ipaddress
import logging
import re
import socket
import struct
import time
from typing import Dict, Any, List, Optional, Tuple
import httpx

logger = logging.getLogger("matter_thread_ai.network_checker")


def _decode_txt_bytes_or_hex(raw: Optional[bytes]) -> str:
    """Decode mDNS TXT value that may be raw binary bytes or ASCII hex/text."""
    if not raw:
        return ""
    if all(32 <= b <= 126 for b in raw):
        return raw.decode("utf-8", errors="ignore").strip()
    return raw.hex().upper()


def _decode_ext_pan_or_mac(raw: Optional[bytes]) -> str:
    """Normalize 8-byte binary or 16-char ASCII hex TXT value into a 16-char uppercase hex string."""
    if not raw:
        return ""
    if len(raw) == 8:
        return raw.hex().upper()
    if all(32 <= b <= 126 for b in raw):
        s = raw.decode("utf-8", errors="ignore").strip().replace(":", "").replace("-", "").upper()
        if s.startswith("0X"):
            s = s[2:]
        if all(c in "0123456789ABCDEF" for c in s) and len(s) >= 8:
            return s.zfill(16)
    return raw.hex().upper()


def _decode_ext_pan_or_hex_len(raw: Optional[bytes]) -> str:
    if not raw:
        return ""
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


# --- Pure-Python DNS / mDNS Wire Format Parser (Zero external dependencies required) ---

def _encode_dns_name(name: str) -> bytes:
    out = bytearray()
    for part in name.strip(".").split("."):
        b = part.encode("utf-8")
        out.append(len(b))
        out.extend(b)
    out.append(0)
    return bytes(out)


def _build_mdns_ptr_query(service_names: List[str], unicast_response: bool = True) -> bytes:
    """Build a multi-question DNS PTR query packet for mDNS (224.0.0.251:5353)."""
    header = struct.pack(">HHHHHH", 0x0000, 0x0000, len(service_names), 0, 0, 0)
    q_bytes = bytearray()
    qclass = 0x8001 if unicast_response else 0x0001  # IN class, bit 15 = QU (unicast response)
    for svc in service_names:
        q_bytes.extend(_encode_dns_name(svc))
        q_bytes.extend(struct.pack(">HH", 12, qclass))  # QTYPE 12 = PTR
    return header + bytes(q_bytes)


def _read_dns_name(packet: bytes, offset: int) -> Tuple[str, int]:
    labels: List[str] = []
    curr = offset
    jumped = False
    next_offset = offset
    visited = set()

    while curr < len(packet):
        if curr in visited:
            break
        visited.add(curr)
        length = packet[curr]
        if length == 0:
            curr += 1
            if not jumped:
                next_offset = curr
            break
        elif (length & 0xC0) == 0xC0:
            if curr + 1 >= len(packet):
                break
            ptr = ((length & 0x3F) << 8) | packet[curr + 1]
            if not jumped:
                next_offset = curr + 2
                jumped = True
            curr = ptr
        else:
            curr += 1
            if curr + length > len(packet):
                break
            labels.append(packet[curr : curr + length].decode("utf-8", errors="ignore"))
            curr += length
            if not jumped:
                next_offset = curr

    return ".".join(labels), next_offset


def _parse_mdns_packet(packet: bytes, sender_ip: str) -> Dict[str, Any]:
    """Parse DNS Answer + Additional records from an mDNS response packet."""
    out: Dict[str, Any] = {"ptr": [], "srv": {}, "txt": {}, "a": {}, "aaaa": {}, "sender_ip": sender_ip}
    if len(packet) < 12:
        return out
    _, _, qdcount, ancount, nscount, arcount = struct.unpack(">HHHHHH", packet[:12])
    offset = 12

    for _ in range(qdcount):
        _, offset = _read_dns_name(packet, offset)
        offset += 4
        if offset > len(packet):
            return out

    total_rr = ancount + nscount + arcount
    for _ in range(total_rr):
        if offset >= len(packet):
            break
        rr_name, offset = _read_dns_name(packet, offset)
        if offset + 10 > len(packet):
            break
        rtype, rclass, ttl, rdlength = struct.unpack(">HHIH", packet[offset : offset + 10])
        offset += 10
        rdata = packet[offset : offset + rdlength]
        r_start = offset
        offset += rdlength
        if offset > len(packet):
            break

        if rtype == 12:  # PTR
            target_name, _ = _read_dns_name(packet, r_start)
            out["ptr"].append((rr_name, target_name))
        elif rtype == 33 and len(rdata) >= 6:  # SRV
            prio, weight, port = struct.unpack(">HHH", rdata[:6])
            target_host, _ = _read_dns_name(packet, r_start + 6)
            out["srv"][rr_name] = {"port": port, "server": target_host}
        elif rtype == 16:  # TXT
            props: Dict[bytes, bytes] = {}
            t_idx = 0
            while t_idx < len(rdata):
                t_len = rdata[t_idx]
                t_idx += 1
                if t_idx + t_len > len(rdata):
                    break
                kv = rdata[t_idx : t_idx + t_len]
                t_idx += t_len
                if b"=" in kv:
                    k, v = kv.split(b"=", 1)
                    props[k] = v
            out["txt"].setdefault(rr_name, {}).update(props)
        elif rtype == 1 and len(rdata) == 4:  # A
            ip_str = socket.inet_ntoa(rdata)
            out["a"].setdefault(rr_name, [])
            if ip_str not in out["a"][rr_name]:
                out["a"][rr_name].append(ip_str)
        elif rtype == 28 and len(rdata) == 16:  # AAAA
            try:
                ip6_str = str(ipaddress.IPv6Address(rdata))
                out["aaaa"].setdefault(rr_name, [])
                if ip6_str not in out["aaaa"][rr_name]:
                    out["aaaa"][rr_name].append(ip6_str)
            except Exception:
                pass

    return out


async def _scan_mdns_via_udp_sockets(duration: float = 1.6) -> Dict[str, Any]:
    """
    Active pure-Python UDP mDNS scanner that queries 224.0.0.251:5353 from an ephemeral socket
    (and shared port 5353 if available). Works even without python-zeroconf or avahi-daemon!
    """
    services = ["_meshcop._udp.local", "_matter._tcp.local", "_matterc._udp.local"]
    sockets_list: List[socket.socket] = []

    try:
        # 1. Ephemeral UDP socket (receives unicast QU replies directly)
        s_ephem = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        s_ephem.setblocking(False)
        s_ephem.bind(("0.0.0.0", 0))
        sockets_list.append(s_ephem)

        # 2. Shared port 5353 multicast listener (receives QM multicast replies)
        try:
            s_mcast = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            s_mcast.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    s_mcast.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except Exception:
                    pass
            s_mcast.setblocking(False)
            s_mcast.bind(("0.0.0.0", 5353))
            mreq = struct.pack("4s4s", socket.inet_aton("224.0.0.251"), socket.inet_aton("0.0.0.0"))
            s_mcast.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            sockets_list.append(s_mcast)
        except Exception:
            pass

        # Send both QU (unicast response) and QM (multicast response) queries
        q_qu = _build_mdns_ptr_query(services, unicast_response=True)
        q_qm = _build_mdns_ptr_query(services, unicast_response=False)
        for sock in sockets_list:
            try:
                sock.sendto(q_qu, ("224.0.0.251", 5353))
                sock.sendto(q_qm, ("224.0.0.251", 5353))
            except Exception:
                pass

        ptr_records: List[Tuple[str, str, str]] = []
        srv_records: Dict[str, Dict[str, Any]] = {}
        txt_records: Dict[str, Dict[bytes, bytes]] = {}
        a_records: Dict[str, List[str]] = {}
        aaaa_records: Dict[str, List[str]] = {}

        loop = asyncio.get_event_loop()
        deadline = loop.time() + duration

        while loop.time() < deadline:
            for sock in sockets_list:
                while True:
                    try:
                        data, addr = sock.recvfrom(9000)
                        parsed = _parse_mdns_packet(data, addr[0])
                        for svc_name, target_inst in parsed["ptr"]:
                            ptr_records.append((svc_name, target_inst, addr[0]))
                        srv_records.update(parsed["srv"])
                        for k, v in parsed["txt"].items():
                            txt_records.setdefault(k, {}).update(v)
                        for k, v in parsed["a"].items():
                            a_records.setdefault(k, []).extend(x for x in v if x not in a_records.get(k, []))
                        for k, v in parsed["aaaa"].items():
                            aaaa_records.setdefault(k, []).extend(x for x in v if x not in aaaa_records.get(k, []))
                    except (BlockingIOError, InterruptedError):
                        break
                    except Exception:
                        break
            await asyncio.sleep(0.08)

        meshcop_list: List[Dict[str, Any]] = []
        matter_op_list: List[Dict[str, Any]] = []
        matter_comm_list: List[Dict[str, Any]] = []
        seen_instances = set()

        # Also inspect any TXT/SRV records whose names end with ._meshcop._udp.local
        all_candidates = list(ptr_records)
        for name_key in list(txt_records.keys()) + list(srv_records.keys()):
            for svc in services:
                if name_key.endswith(svc):
                    all_candidates.append((svc, name_key, ""))

        for svc_name, inst_full, sender_ip in all_candidates:
            if inst_full in seen_instances:
                continue
            seen_instances.add(inst_full)

            props = txt_records.get(inst_full, {})
            srv = srv_records.get(inst_full, {})
            server_host = srv.get("server", "")
            port = srv.get("port", 0)
            v4_list = list(a_records.get(server_host, []))
            if sender_ip and "." in sender_ip and sender_ip not in v4_list:
                v4_list.append(sender_ip)
            v6_list = list(aaaa_records.get(server_host, []))
            inst_short = inst_full.replace(f".{svc_name}", "").replace("._meshcop._udp.local", "").replace("._matter._tcp.local", "").replace("._matterc._udp.local", "")

            if "_meshcop._udp" in svc_name or "_meshcop._udp" in inst_full:
                nn = _decode_txt_bytes_or_hex(props.get(b"nn"))
                xp = _decode_ext_pan_or_mac(props.get(b"xp"))
                vn = _decode_txt_bytes_or_hex(props.get(b"vn"))
                mn = _decode_txt_bytes_or_hex(props.get(b"mn"))
                tv = _decode_txt_bytes_or_hex(props.get(b"tv"))
                xa = _decode_ext_pan_or_mac(props.get(b"xa"))
                ba = _decode_ext_pan_or_hex_len(props.get(b"ba"))
                dn = _decode_txt_bytes_or_hex(props.get(b"dn"))
                sb_info = _decode_state_bitmap(props.get(b"sb"))

                meshcop_list.append({
                    "instance_name": inst_short,
                    "service_name": inst_full,
                    "server": server_host or sender_ip,
                    "port": port,
                    "network_name": nn or inst_short,
                    "extended_pan_id": xp or "UNKNOWN",
                    "vendor_name": vn,
                    "model_name": mn,
                    "thread_version": tv,
                    "ext_address": xa,
                    "border_agent_id": ba,
                    "domain_name": dn,
                    "state_bitmap": sb_info,
                    "ipv6_addresses": v6_list,
                    "ipv4_addresses": v4_list,
                    "addresses": v6_list + v4_list,
                    "source": "Live UDP mDNS (_meshcop._udp)",
                })
            elif "_matter._tcp" in svc_name or "_matter._tcp" in inst_full:
                fabric_part = ""
                node_id_int = None
                if "-" in inst_short:
                    parts = inst_short.split("-")
                    fabric_part = parts[0]
                    try:
                        node_id_int = int(parts[1], 16)
                    except ValueError:
                        pass
                matter_op_list.append({
                    "instance_name": inst_short,
                    "compressed_fabric_id": fabric_part,
                    "node_id": node_id_int,
                    "server": server_host,
                    "port": port,
                    "ipv6_addresses": v6_list,
                    "ipv4_addresses": v4_list,
                })
            elif "_matterc._udp" in svc_name or "_matterc._udp" in inst_full:
                matter_comm_list.append({
                    "instance_name": inst_short,
                    "server": server_host,
                    "port": port,
                    "ipv6_addresses": v6_list,
                    "ipv4_addresses": v4_list,
                })

        return {
            "meshcop_border_routers": meshcop_list,
            "matter_operational_nodes": matter_op_list,
            "matter_commissionable_nodes": matter_comm_list,
        }
    finally:
        for sock in sockets_list:
            try:
                sock.close()
            except Exception:
                pass


class NetworkChecker:
    @staticmethod
    async def inspect_ipv6_routes() -> Dict[str, Any]:
        """
        Inspect kernel IPv6 routing table and Neighbor Discovery cache for Thread ULA
        prefixes (fd00::/8) advertised via ICMPv6 Route Information Options (RIO).
        """
        routes: List[str] = []
        ula_routes_detailed: List[Dict[str, str]] = []
        thread_ula_prefixes: List[str] = []
        neighbors: List[Dict[str, str]] = []
        has_thread_ula_route = False

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
    async def inspect_mdns_discovery(scan_duration: float = 1.6) -> Dict[str, Any]:
        """
        Perform a REAL live mDNS scan on the local network combining:
          1. Built-in pure-Python UDP DNS-SD socket scanner (zero external dependencies, never conflicts with port 5353)
          2. Python `zeroconf` (`AsyncZeroconf`) if installed
        """
        meshcop_routers: List[Dict[str, Any]] = []
        matter_operational_nodes: List[Dict[str, Any]] = []
        matter_commissionable_nodes: List[Dict[str, Any]] = []
        seen_router_keys = set()
        seen_op_keys = set()
        scanner_backend = "udp_dns_sd"
        error_msg = None

        # 1. Run pure-Python UDP DNS-SD scan (works in 100% of environments)
        try:
            udp_res = await _scan_mdns_via_udp_sockets(duration=scan_duration)
            for r in udp_res.get("meshcop_border_routers", []):
                k = r.get("border_agent_id") or r.get("ext_address") or f"{r.get('instance_name')}_{r.get('extended_pan_id')}"
                if k not in seen_router_keys:
                    seen_router_keys.add(k)
                    meshcop_routers.append(r)
            for op in udp_res.get("matter_operational_nodes", []):
                k = op.get("instance_name")
                if k not in seen_op_keys:
                    seen_op_keys.add(k)
                    matter_operational_nodes.append(op)
            matter_commissionable_nodes.extend(udp_res.get("matter_commissionable_nodes", []))
        except Exception as e:
            error_msg = str(e)
            logger.debug("Pure-Python UDP mDNS scan error: %s", e)

        # 2. Also run AsyncZeroconf if available to enrich any additional multicast records
        azc = None
        browser = None
        try:
            from zeroconf import ServiceStateChange, Zeroconf
            from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

            scanner_backend = "udp_dns_sd+zeroconf"
            discovered_targets: List[tuple] = []

            def on_service_state_change(zeroconf: Zeroconf, service_type: str, name: str, state_change: ServiceStateChange) -> None:
                if state_change is ServiceStateChange.Added:
                    discovered_targets.append((service_type, name))

            azc = AsyncZeroconf()
            services = ["_meshcop._udp.local.", "_matter._tcp.local.", "_matterc._udp.local."]
            browser = AsyncServiceBrowser(azc.zeroconf, services, handlers=[on_service_state_change])

            await asyncio.sleep(min(scan_duration, 1.2))

            async def resolve_one(svc_type: str, svc_name: str):
                info = AsyncServiceInfo(svc_type, svc_name)
                await info.async_request(azc.zeroconf, 1500)
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

                    entry = {
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
                    }
                    k = ba or xa or f"{instance_label}_{xp}"
                    if k not in seen_router_keys:
                        seen_router_keys.add(k)
                        meshcop_routers.append(entry)

                elif svc_type == "_matter._tcp.local.":
                    if instance_label not in seen_op_keys:
                        seen_op_keys.add(instance_label)
                        fabric_part = ""
                        node_id_int = None
                        if "-" in instance_label:
                            parts = instance_label.split("-")
                            fabric_part = parts[0]
                            try:
                                node_id_int = int(parts[1], 16)
                            except ValueError:
                                pass
                        matter_operational_nodes.append({
                            "instance_name": instance_label,
                            "compressed_fabric_id": fabric_part,
                            "node_id": node_id_int,
                            "server": (info.server or "").rstrip("."),
                            "port": info.port,
                            "ipv6_addresses": ipv6_addrs,
                            "ipv4_addresses": ipv4_addrs,
                        })
        except Exception as e:
            logger.debug("Zeroconf scan skipped/failed: %s", e)
        finally:
            if browser is not None:
                try:
                    await browser.async_cancel()
                except Exception:
                    pass
            if azc is not None:
                try:
                    await azc.async_close()
                except Exception:
                    pass

        return {
            "mdns_capable": True,
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
            "http://172.30.32.1:8081",
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
        """Execute a real ICMP/ICMPv6 ping against a target IPv6 or IPv4 address."""
        if not ip_addr:
            return {"ip": ip_addr, "reachable": False, "error": "Empty address"}

        clean_ip = ip_addr.split("/")[0].strip()
        is_ipv6 = ":" in clean_ip
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

            loss_pct = 0.0 if reachable else 100.0
            loss_m = re.search(r"(\d+(?:\.\d+)?)%\s*packet loss", output)
            if loss_m:
                loss_pct = float(loss_m.group(1))

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
        """Actively ping discovered Border Routers and Matter-over-Thread nodes via ICMPv6/ICMPv4."""
        tasks = []
        target_meta = []

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
