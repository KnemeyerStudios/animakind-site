#!/usr/bin/env python3
"""Recheck the candidate records bundle. Run from this directory: python3 verify.py
Uses only the standard library. Exit code 0 = every check passed.

What this can and cannot show: it rechecks that the ledger's commit graph is one
unbroken, acyclic chain from the genesis commit, that the stated events fall where
the paper says, and that the counts add up. It cannot recompute a commit hash from
content (content is not in the bundle); full verification of a hash is possible only
for a party given the repository itself."""
import csv, json, os, re, sys, datetime, collections

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []
notes = []

def check(name, ok, detail=''):
    print(('PASS  ' if ok else 'FAIL  ') + name + (('  [' + str(detail) + ']') if detail != '' else ''))
    if not ok:
        fails.append(name)

def load(n):
    return json.load(open(os.path.join(HERE, n)))

def utc(iso):
    return datetime.datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(datetime.timezone.utc)

# ---------- 1. hash chain
rows = list(csv.DictReader(open(os.path.join(HERE, 'ledger-chain.tsv')), delimiter='\t'))
hexre = re.compile(r'^[0-9a-f]{40}$')
seen = set()
roots = []
bad_format = bad_parent = dup = 0
merges = 0
for r in rows:
    h = r['commit']
    ps = [p for p in r['parents'].split(',') if p]
    if not hexre.match(h):
        bad_format += 1
    if h in seen:
        dup += 1
    if not ps:
        roots.append(h)
    if len(ps) > 1:
        merges += 1
    for p in ps:
        if not hexre.match(p):
            bad_format += 1
        if p not in seen:          # parent must already have appeared: acyclic and complete
            bad_parent += 1
    seen.add(h)
check('chain: every id is a 40-hex digest', bad_format == 0, bad_format)
check('chain: no duplicate commits', dup == 0, dup)
check('chain: every parent appears earlier (no breaks, no cycles)', bad_parent == 0, bad_parent)
check('chain: exactly one root (genesis)', len(roots) == 1, len(roots))
# every commit descends from genesis
anc = {}
for r in rows:
    ps = [p for p in r['parents'].split(',') if p]
    anc[r['commit']] = (not ps) or all(anc.get(p, False) for p in ps)
check('chain: every commit descends from the genesis commit', all(anc.values()))
A = load('ledger-anchors.json')
check('chain: root equals the genesis commit in anchors', roots == [A['genesis']['commit']])
check('chain: size not smaller than the count recorded when the bundle was built',
      len(rows) >= A['ledger_commit_count'], '%d rows, %d at build' % (len(rows), A['ledger_commit_count']))
check('chain: merge count at least the count recorded at build', merges >= A['merge_commit_count'], merges)
for w in ('power_loss_window_2026_09_03', 'migration_day_2026_08_04'):
    check('anchors: every commit in %s is in the chain' % w, all(c['commit'] in seen for c in A[w]))

# ---------- 2. genesis time and UCR
U = load('ucr.json')
E = U['entries']
check('genesis: ledger root author time == UCR GENESIS instant',
      utc(A['genesis']['author_time']) == utc(E[0]['timestamp_utc']), E[0]['timestamp_utc'])
check('ucr: three entries GENESIS, ENGINE_MIGRATION, RUNTIME_FAILURE',
      [e['event'] for e in E] == ['GENESIS', 'ENGINE_MIGRATION', 'RUNTIME_FAILURE'])
check('ucr: timestamps strictly increasing', [e['timestamp_utc'] for e in E] == sorted(e['timestamp_utc'] for e in E))
check('ucr: binding after each entry == binding before the next',
      E[0]['uab_after'] == E[1]['uab_before'] and E[1]['uab_after'] == E[2]['uab_before'])
check('ucr: migration changes the binding and leaves the UIV untouched',
      E[1]['uab_before'] != E[1]['uab_after'] and E[1]['uiv_before'] == E[1]['uiv_after'])
check('ucr: failure changes neither binding nor UIV',
      E[2]['uab_before'] == E[2]['uab_after'] and E[2]['uiv_before'] == E[2]['uiv_after'])
B = load('binding-designation.json')
check('binding: designation == UCR migration uab_after', B['designation'] == E[1]['uab_after'])
check('binding: supersedes == UCR migration uab_before', B['supersedes'] == E[1]['uab_before'])
mig = [c for c in A['migration_day_2026_08_04']]
mt = utc(E[1]['timestamp_utc'])
check('migration: ledger has commits before and after the UCR migration instant on the same UTC day span',
      any(c['relative_to_ucr_migration_instant'] == 'before' for c in mig) and any(c['relative_to_ucr_migration_instant'] == 'after' for c in mig),
      '%d commits on the local day' % len(mig))

# ---------- 3. power loss bracket
ft = utc(E[2]['timestamp_utc'])
w = A['power_loss_window_2026_09_03']
hostA = [c for c in w if c['origin_class'] == 'host-A']
before = [c for c in hostA if utc(c['author_time_utc']) < ft]
after = [c for c in hostA if utc(c['author_time_utc']) > ft]
lb = max(before, key=lambda c: c['author_time_utc']) if before else None
fa = min(after, key=lambda c: c['author_time_utc']) if after else None
check('power loss: a primary-host commit precedes the failure and one follows', bool(lb and fa))
if lb and fa:
    check('power loss: last primary-host commit before is 20:30:01 EDT', utc(lb['author_time_utc']).strftime('%H:%M:%S') == '00:30:01', lb['author_time'])
    check('power loss: first primary-host commit after is 20:55:01 EDT', utc(fa['author_time_utc']).strftime('%H:%M:%S') == '00:55:01', fa['author_time'])
    # no primary-host commit inside the gap
    inside = [c for c in hostA if lb['author_time_utc'] < c['author_time_utc'] < fa['author_time_utc']]
    check('power loss: no primary-host commit inside the gap', not inside, len(inside))
    other = [c['author_time'] for c in w if c['origin_class'] != 'host-A' and lb['author_time_utc'] < c['author_time_utc'] < fa['author_time_utc']]
    notes.append('NOTE: %d commit(s) from another machine fall inside the primary-host gap (%s). The paper\'s statement is about the host that lost power; the ledger itself was not idle.' % (len(other), ', '.join(other)))
    notes.append('NOTE: 20 min 43 s of lost context in the paper = journal last entry 20:50:44 minus 20:30:01. The journal is not in this bundle (rotated off the box); only the ledger half is checkable here: gap = %d s.' % (utc(fa['author_time_utc']) - utc(lb['author_time_utc'])).total_seconds())
check('power loss: 20:50:44 - 20:30:01 == 20 min 43 s (arithmetic of the paper figure)', (50 * 60 + 44) - (30 * 60 + 1) == 20 * 60 + 43)
check('power loss: 20:52:10 - 20:50:44 == 86 s (paper outage figure)', (52 * 60 + 10) - (50 * 60 + 44) == 86)

# ---------- 5. engine strings
rowsE = list(csv.DictReader(open(os.path.join(HERE, 'engine-strings.tsv')), delimiter='\t'))
pt = {r['engine_string']: r for r in rowsE if r['source'] == 'paper-table'}
check('engines: paper-table counts 697 and 822', pt['claude-opus-4-8']['records'] == '697' and pt['claude-opus-5']['records'] == '822')
check('engines: opus-5 first date is the UCR migration date', pt['claude-opus-5']['first_date'] == E[1]['timestamp_utc'][:10])
check('engines: opus-4-8 last date precedes the second spans end', pt['claude-opus-4-8']['last_date'] < pt['claude-opus-5']['last_date'])

# ---------- 6. truncation
T = load('truncation.json')
size = T['identity_document_size_bytes_at_2026-09-05_ledger_state']
check('truncation: document exceeds the 10,000-byte limit, delivery was 2,048 bytes',
      size is not None and size > T['injection_limit_bytes'] > T['delivered_bytes_when_over_limit'] == 2048, size)
check('truncation: ledger commit used for the size is in the chain', T['ledger_commit_used_for_size'] in seen)
L = list(csv.DictReader(open(os.path.join(HERE, 'loader-commits.tsv')), delimiter='\t'))
check('loader: every listed commit is in the chain', all(r['commit'] in seen for r in L), len(L))

# ---------- 7. identity-path commits around the migration
I = list(csv.DictReader(open(os.path.join(HERE, 'identity-path-commits.tsv')), delimiter='\t'))
check('identity: every listed commit is in the chain', all(r['commit'] in seen for r in I), len(I))
same_day = [r for r in I if r['author_time'].startswith('2026-08-04') or r['author_time'].startswith('2026-08-05')]
check('identity: no identity-path commit on the migration day (2026-08-04) or the next', not same_day, len(same_day))
nxt = [float(r['days_from_migration_instant']) for r in I if float(r['days_from_migration_instant']) > 0]
notes.append('NOTE: first identity-path commit after the migration instant is %.1f days later; those later commits exist and whether they relate to the migration is a judgment the bundle does not make.' % min(nxt))

for n in notes:
    print(n)
print('\nRESULT: %s (%d failed)' % ('ALL CHECKS PASSED' if not fails else 'FAILED', len(fails)))
sys.exit(1 if fails else 0)
