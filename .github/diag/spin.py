# Prints the threads of a spindump report that used the CPU, heaviest first, with their stacks.
import re, sys
text = open(sys.argv[1], errors="replace").read().split("\n")
threads, cur = [], None
for line in text:
    m = re.match(r"^\s{2}Thread 0x[0-9a-f]+.*?cpu time ([\d.]+)(ms|s)", line)
    if m:
        cpu = float(m.group(1)) / (1000 if m.group(2) == "ms" else 1)
        cur = [cpu, [line.strip()]]; threads.append(cur); continue
    if line.startswith("  Thread 0x"):
        cur = [0.0, [line.strip()]]; threads.append(cur); continue
    if cur is not None:
        if not line.strip() or re.match(r"^\S", line):
            cur = None
        elif len(cur[1]) < 45:
            cur[1].append(line.rstrip()[:220])
for line in text[:40]:
    if re.match(r"^(Duration|Steps|Sampling interval|Process|CPU Time|Num threads|Footprint)", line):
        print(line)
for cpu, lines in sorted(threads, key=lambda t: -t[0])[:8]:
    print(f"\n### {cpu*1000:.0f} ms of CPU")
    print("\n".join(lines))
