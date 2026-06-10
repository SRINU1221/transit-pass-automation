"""patch_preview.py - patches app.py preview section by line numbers"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

with open('app.py', encoding='utf-8') as f:
    lines = f.readlines()

# Find the preview section by searching for the unique marker
start_idx = None
end_idx = None
for i, line in enumerate(lines):
    if '# \u2500\u2500 Preview' in line and 'if st.session_state' not in line:
        start_idx = i
    if start_idx is not None and "st.markdown('</div>'" in line and i > start_idx:
        end_idx = i
        break

if start_idx is None or end_idx is None:
    print(f"Could not find preview block. start={start_idx} end={end_idx}")
    for i, l in enumerate(lines[283:298], 284):
        print(f"  {i}: {repr(l.rstrip())[:80]}")
    sys.exit(1)

print(f"Found preview block: lines {start_idx+1} to {end_idx+1}")

# Grab the original lines to show what we're replacing
print("Original:")
for i in range(start_idx, end_idx+1):
    print(f"  {i+1}: {lines[i].rstrip()[:80]}")

# Build replacement lines (preserving indentation style)
new_lines = [
    "    # \u2500\u2500 Preview \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n",
    "    if st.session_state.records:\n",
    "        recs = st.session_state.records\n",
    "        st.markdown(\n",
    lines[start_idx + 3].replace(
        "{len(st.session_state.records)}", "{len(recs)}"
    ),
    "            unsafe_allow_html=True\n",
    "        )\n",
    "        st.dataframe(records_to_dataframe(recs), use_container_width=True, height=220)\n",
    "        r0 = recs[0]\n",
    "        st.info(\n",
    "            f\"\u270f\ufe0f CONSIGNEE INFO per row \u2014 \"\n",
    "            f\"Dispatch Qty: {r0.get('dispatch_qty','?')} | \"\n",
    "            f\"Sale Value: {r0.get('sales_value','?')} | \"\n",
    "            f\"Stationery No: {r0.get('stationary_no','?')} (each row gets its own)\"\n",
    "        )\n",
    "        st.markdown('</div>', unsafe_allow_html=True)\n",
]

# Replace lines
lines[start_idx:end_idx+1] = new_lines

with open('app.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("\nSUCCESS: Preview section patched.")
