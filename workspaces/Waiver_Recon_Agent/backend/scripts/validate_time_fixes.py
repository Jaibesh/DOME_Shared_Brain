# Quick validation of time parser and slot selection fixes
import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding='utf-8')

from data_mapper import parse_time_string, select_best_time_slot

# Test parse_time_string with all format variants
print("=== parse_time_string ===")
tests = ['10am', '10AM', '5pm', '5PM', '9am', '5:15 PM', '8:30 am', '5:30pm', '12pm', '14:30', '4:45pm']
for t in tests:
    result = parse_time_string(t)
    print(f"  OK: {t!r:14s} => {result.strftime('%I:%M %p')}")

print()
print("=== select_best_time_slot ===")
cases = [
    ('5:30pm', ['9am', '5pm'], '5pm'),     # was incorrectly picking 9am (nearest distance fix)
    ('10am', ['9am', '2pm'], '9am'),        # target=10am, nearest <= is 9am
    ('4pm', ['9am', '5pm'], '5pm'),         # 4pm -> both are after, nearest is 5pm not 9am
    ('8:30am', ['9am', '5pm'], '9am'),      # 8:30am closest-after is 9am
    ('12pm', ['8am', '9am', '10am'], '10am'),  # 12pm, nearest <= is 10am
    ('5:15 PM', ['9am', '5pm'], '5pm'),     # 5:15pm, nearest <= is 5pm
    ('4:45pm', ['9am', '5pm'], '5pm'),      # 4:45pm -> nearest is 5pm
    ('9am', ['9am', '5pm'], '9am'),         # exact match
]
all_pass = True
for target, avail, expected in cases:
    result = select_best_time_slot(avail, target)
    status = 'OK' if result == expected else 'FAIL'
    if result != expected:
        all_pass = False
    print(f"  [{status}] target={target!r:12s} avail={str(avail):30s} => {result!r:8s} (expected {expected!r})")

print()
if all_pass:
    print("ALL TIME TESTS PASS")
else:
    print("SOME TESTS FAILED!")
