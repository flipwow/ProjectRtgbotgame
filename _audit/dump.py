import io, sys

path = "main.py"
if len(sys.argv) > 1:
    path = sys.argv[1]
start = int(sys.argv[2]) if len(sys.argv) > 2 else 1
end = int(sys.argv[3]) if len(sys.argv) > 3 else 10**9
lines = io.open(path, encoding="utf-8").read().splitlines()
out = []
for i, line in enumerate(lines[start - 1:end], start=start):
    out.append("%5d: %s" % (i, line))
io.open("_audit/_view.txt", "w", encoding="utf-8").write("\n".join(out))
print("wrote", len(out), "lines")
