"""Generated history, convergence, and mutation-adequacy tests for Reconcile."""

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

FILES = Path(os.environ.get("TASK_FILES", "/app/files"))
WORK = Path(os.environ.get("TASK_HIDDEN_WORK", "/tmp/raft-hidden"))


def _stage():
    shutil.rmtree(WORK, ignore_errors=True)
    (WORK / "raft").mkdir(parents=True)
    (WORK / "cmd" / "raft-reconcile").mkdir(parents=True)
    (WORK / "hidden_tests").mkdir()
    shutil.copy2(FILES / "go.mod", WORK / "go.mod")
    for name in ("types.go", "reconcile.go"):
        source = FILES / "raft" / name
        assert source.is_file() and not source.is_symlink()
        shutil.copy2(source, WORK / "raft" / name)
    shutil.copy2(FILES / "cmd" / "raft-reconcile" / "main.go", WORK / "cmd" / "raft-reconcile" / "main.go")


GENERATED_GO = r'''package hidden_tests

import (
    "math/rand"
    "reflect"
    "testing"

    "raftsnapshot/raft"
)

func clone(s raft.State) raft.State {
    s.Entries = append([]raft.Entry(nil), s.Entries...)
    return s
}

// oracle is deliberately independent from the candidate kernel.
func oracle(in raft.State, term uint64, q raft.AppendRequest) (raft.State, uint64, raft.AppendResult) {
    s := clone(in)
    reject := func() (raft.State, uint64, raft.AppendResult) { return s, term, raft.AppendResult{} }
    if q.Term < term { return reject() }
    if q.Term > term { term = q.Term }
    if q.PrevIndex < s.Snapshot.Index || q.PrevIndex > s.LastIndex() { return reject() }
    if q.PrevIndex == s.Snapshot.Index {
        if q.PrevTerm != s.Snapshot.Term { return reject() }
    } else {
        p := q.PrevIndex - s.Snapshot.Index - 1
        if p >= uint64(len(s.Entries)) || s.Entries[p].Term != q.PrevTerm { return reject() }
    }
    for i, e := range q.Entries {
        if e.Index != q.PrevIndex+1+uint64(i) { return reject() }
    }
    first := len(q.Entries)
    for i, e := range q.Entries {
        p := int(e.Index - s.Snapshot.Index - 1)
        if p >= len(s.Entries) { first = i; break }
        if s.Entries[p] != e { first = i; break }
    }
    if first < len(q.Entries) {
        conflict := q.Entries[first].Index
        if conflict <= s.Commit && conflict <= s.LastIndex() { return reject() }
        keep := int(conflict - s.Snapshot.Index - 1)
        if keep < len(s.Entries) { s.Entries = append([]raft.Entry(nil), s.Entries[:keep]...) }
        s.Entries = append(s.Entries, q.Entries[first:]...)
    }
    last := s.LastIndex()
    if q.LeaderCommit > s.Commit {
        s.Commit = q.LeaderCommit
        if s.Commit > last { s.Commit = last }
    }
    return s, term, raft.AppendResult{Accepted: true, MatchIndex: q.PrevIndex + uint64(len(q.Entries))}
}

func equalRun(t *testing.T, s raft.State, term uint64, q raft.AppendRequest) (raft.State, uint64, raft.AppendResult) {
    t.Helper()
    ws, wt, wr := oracle(s, term, q)
    gs, gt, gr := raft.Reconcile(s, term, q)
    if !reflect.DeepEqual(gs, ws) || gt != wt || gr != wr {
        t.Fatalf("mismatch\nstate=%#v term=%d request=%#v\n got=%#v %d %#v\nwant=%#v %d %#v", s, term, q, gs, gt, gr, ws, wt, wr)
    }
    if err := gs.Validate(); err != nil { t.Fatalf("invalid output: %v", err) }
    return gs, gt, gr
}

func history(snapshot uint64, terms []uint64, label string, commit uint64) raft.State {
    e := make([]raft.Entry, len(terms))
    for i, term := range terms { e[i] = raft.Entry{Index: snapshot+1+uint64(i), Term: term, Data: label+string(rune('a'+i%26))} }
    snapTerm := uint64(1)
    return raft.State{Snapshot: raft.Snapshot{Index: snapshot, Term: snapTerm}, Entries: e, Commit: commit}
}

func TestGeneratedLeaderFollowerHistoriesConverge(t *testing.T) {
    rng := rand.New(rand.NewSource(0x5a17))
    for n := 0; n < 160; n++ {
        snap := uint64(rng.Intn(30))
        count := 1 + rng.Intn(35)
        terms := make([]uint64, count)
        x := uint64(2)
        for i := range terms { if i > 0 && rng.Intn(4) == 0 { x++ }; terms[i] = x }
        // Keep at least one leader entry in the request; an empty heartbeat must
        // not truncate a follower-only suffix.
        common := rng.Intn(count)
        leader := history(snap, terms, "L", snap)
        followerTerms := append([]uint64(nil), terms[:common]...)
        for i := common; i < count+rng.Intn(5); i++ { followerTerms = append(followerTerms, x+10) }
        follower := history(snap, followerTerms, "L", snap+uint64(common))
        for i := common; i < len(follower.Entries); i++ { follower.Entries[i].Data = "conflict" }
        prevTerm := follower.Snapshot.Term
        if common > 0 { prevTerm = leader.Entries[common-1].Term }
        suffix := append([]raft.Entry(nil), leader.Entries[common:]...)
        q := raft.AppendRequest{Term: x+20, PrevIndex: snap+uint64(common), PrevTerm: prevTerm,
            Entries: suffix, LeaderCommit: leader.LastIndex()}
        got, term, result := equalRun(t, follower, x+20, q)
        if !result.Accepted || !reflect.DeepEqual(got.Entries, leader.Entries) || got.Commit != leader.LastIndex() { t.Fatal("did not converge") }
        // Metamorphism: a heartbeat at the match point changes nothing and reports that point.
        again, _, rr := equalRun(t, got, term, raft.AppendRequest{Term: term, PrevIndex: got.LastIndex(),
            PrevTerm: got.Entries[len(got.Entries)-1].Term, LeaderCommit: got.Commit})
        if !reflect.DeepEqual(got, again) || rr.MatchIndex != got.LastIndex() { t.Fatal("heartbeat not idempotent") }
    }
}

func TestGeneratedRequestsAgainstIndependentOracle(t *testing.T) {
    rng := rand.New(rand.NewSource(0xc0111de))
    for n := 0; n < 500; n++ {
        snap := uint64(rng.Intn(20))
        count := rng.Intn(20)
        terms := make([]uint64, count)
        for i := range terms { terms[i] = 2 + uint64(i/4) }
        commit := snap
        if count > 0 { commit += uint64(rng.Intn(count+1)) }
        s := history(snap, terms, "v", commit)
        mode := rng.Intn(8)
        prev := snap + uint64(rng.Intn(count+1))
        prevTerm := s.Snapshot.Term
        if prev > snap { prevTerm = s.Entries[prev-snap-1].Term }
        q := raft.AppendRequest{Term: 20, PrevIndex: prev, PrevTerm: prevTerm, LeaderCommit: snap+uint64(rng.Intn(count+4))}
        switch mode {
        case 0: q.Term = 19
        case 1: q.PrevIndex = snap-uint64(boolInt(snap > 0))
        case 2: q.PrevIndex = s.LastIndex()+1
        case 3: q.PrevTerm++
        case 4: q.Entries = []raft.Entry{{Index: prev+2, Term: 20, Data: "gap"}}
        case 5: q.Entries = []raft.Entry{{Index: prev+1, Term: 20, Data: "replace"}}
        case 6:
            if prev < s.LastIndex() { q.Entries = append([]raft.Entry(nil), s.Entries[prev-snap:prev-snap+1]...) }
        case 7: q.Term = 21
        }
        equalRun(t, s, 20, q)
    }
}

func boolInt(v bool) uint64 { if v { return 1 }; return 0 }

func TestSnapshotAndArithmeticBoundaries(t *testing.T) {
    s := raft.State{Snapshot: raft.Snapshot{Index: 50, Term: 7}, Commit: 50}
    equalRun(t, s, 9, raft.AppendRequest{Term: 9, PrevIndex: 49, PrevTerm: 7})
    equalRun(t, s, 9, raft.AppendRequest{Term: 9, PrevIndex: 50, PrevTerm: 8})
    equalRun(t, s, 9, raft.AppendRequest{Term: 10, PrevIndex: 50, PrevTerm: 7,
        Entries: []raft.Entry{{Index: 51, Term: 10, Data: "x"}}, LeaderCommit: ^uint64(0)})
}

func TestCommittedPrefixDataAndTermAreImmutable(t *testing.T) {
    s := history(10, []uint64{2,2,3,3}, "v", 13)
    for index := uint64(11); index <= 13; index++ {
        prev := index-1; pt := s.Snapshot.Term
        if prev > s.Snapshot.Index { pt = s.Entries[prev-s.Snapshot.Index-1].Term }
        for _, e := range []raft.Entry{{Index:index, Term:99, Data:"v"}, {Index:index, Term:s.Entries[index-11].Term, Data:"changed"}} {
            q := raft.AppendRequest{Term: 100, PrevIndex: prev, PrevTerm: pt, Entries: []raft.Entry{e}, LeaderCommit: 14}
            got, term, r := equalRun(t, s, 50, q)
            if r.Accepted || term != 100 || !reflect.DeepEqual(got, s) { t.Fatal("committed prefix changed") }
        }
    }
}

func TestRetryShorterThanLocalSuffixDoesNotTruncate(t *testing.T) {
    s := history(3, []uint64{2,2,3,3,4}, "v", 4)
    q := raft.AppendRequest{Term: 8, PrevIndex: 4, PrevTerm: 2, Entries: append([]raft.Entry(nil), s.Entries[1:3]...), LeaderCommit: 6}
    got, term, r := equalRun(t, s, 8, q)
    if len(got.Entries) != len(s.Entries) || r.MatchIndex != 6 { t.Fatal("retry truncated suffix or wrong match index") }
    twice, _, _ := equalRun(t, got, term, q)
    if !reflect.DeepEqual(got, twice) { t.Fatal("duplicate changed state") }
}

func TestOutputsNeverAliasInputsOrRequest(t *testing.T) {
    s := history(2, []uint64{2,2}, "v", 2)
    q := raft.AppendRequest{Term: 5, PrevIndex: 4, PrevTerm: 2}
    got, _, _ := raft.Reconcile(s, 5, q)
    got.Entries[0].Data = "mutated"
    if s.Entries[0].Data == "mutated" { t.Fatal("rejected output aliases state") }

    q = raft.AppendRequest{Term: 5, PrevIndex: 2, PrevTerm: 1, Entries: []raft.Entry{{3,5,"new"}}}
    got, _, _ = raft.Reconcile(raft.State{Snapshot: s.Snapshot, Commit:2}, 5, q)
    q.Entries[0].Data = "mutated"
    if got.Entries[0].Data == "mutated" { t.Fatal("accepted output aliases request") }
}

func TestStaleAndNewTermSemantics(t *testing.T) {
    s := history(4, []uint64{3,4}, "v", 4)
    stale := raft.AppendRequest{Term: 8, PrevIndex: 4, PrevTerm: 1, Entries: []raft.Entry{{5,99,"bad"}}}
    got, term, r := equalRun(t, s, 9, stale)
    if term != 9 || r.Accepted || !reflect.DeepEqual(got, s) { t.Fatal("stale leader accepted") }
    newerMismatch := raft.AppendRequest{Term: 11, PrevIndex: 5, PrevTerm: 99}
    got, term, r = equalRun(t, s, 9, newerMismatch)
    if term != 11 || r.Accepted || !reflect.DeepEqual(got, s) { t.Fatal("new term not observed cleanly") }
}
'''


def test_hidden_generated_metamorphic_and_oracle_suite():
    _stage()
    (WORK / "hidden_tests" / "generated_test.go").write_text(GENERATED_GO)
    result = subprocess.run(
        ["go", "test", "./..."], cwd=WORK, text=True, capture_output=True, timeout=240,
        env={**os.environ, "GOTOOLCHAIN": "local", "GOPROXY": "off", "GOSUMDB": "off"},
    )
    assert result.returncode == 0, result.stdout[-5000:] + result.stderr[-5000:]


def test_hidden_exact_artifact_and_no_bypass_surface():
    artifact = FILES / "raft" / "reconcile.go"
    assert artifact.is_file() and not artifact.is_symlink()
    source = artifact.read_text()
    forbidden = ("os/exec", "unsafe", "go:linkname", "//go:generate", "net/", "plugin")
    assert not any(token in source for token in forbidden)
    assert "func Reconcile(" in source
    allowed_go = {
        "raft/types.go", "raft/reconcile.go", "cmd/raft-reconcile/main.go",
        "public_tests/reconcile_test.go",
    }
    actual_go = {str(path.relative_to(FILES)) for path in FILES.rglob("*.go")}
    assert actual_go == allowed_go, f"unexpected Go source: {actual_go - allowed_go}"
    assert hashlib.sha256((FILES / "go.mod").read_bytes()).hexdigest() == "dd162601755fe6ea5b0231a8e4ae44238016ee01b07b6d9ad77a02af313caed3"
