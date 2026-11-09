package public_tests

import (
	"reflect"
	"testing"

	"raftsnapshot/raft"
)

func base() raft.State {
	return raft.State{Snapshot: raft.Snapshot{Index: 5, Term: 2}, Commit: 6,
		Entries: []raft.Entry{{6, 3, "a"}, {7, 3, "b"}, {8, 4, "old"}}}
}

func TestNormalConflictRepair(t *testing.T) {
	s, term, r := raft.Reconcile(base(), 5, raft.AppendRequest{Term: 5, PrevIndex: 7, PrevTerm: 3,
		Entries: []raft.Entry{{8, 5, "new"}, {9, 5, "tail"}}, LeaderCommit: 8})
	if !r.Accepted || r.MatchIndex != 9 || term != 5 || s.Commit != 8 || s.Entries[2].Data != "new" {
		t.Fatalf("unexpected result: %#v %d %#v", s, term, r)
	}
}

func TestEdgeSnapshotBoundary(t *testing.T) {
	s := raft.State{Snapshot: raft.Snapshot{Index: 40, Term: 7}, Commit: 40}
	got, _, result := raft.Reconcile(s, 9, raft.AppendRequest{Term: 9, PrevIndex: 40, PrevTerm: 7,
		Entries: []raft.Entry{{41, 9, "x"}}, LeaderCommit: 41})
	if !result.Accepted || got.LastIndex() != 41 || got.Commit != 41 { t.Fatalf("%#v %#v", got, result) }
}

func TestInvariantCommittedPrefixCannotChange(t *testing.T) {
	want := base()
	got, _, result := raft.Reconcile(want, 5, raft.AppendRequest{Term: 6, PrevIndex: 5, PrevTerm: 2,
		Entries: []raft.Entry{{6, 6, "rewrite"}}})
	if result.Accepted || !reflect.DeepEqual(got, want) { t.Fatalf("committed rewrite: %#v %#v", got, result) }
}

func TestDeterministicDuplicateRerun(t *testing.T) {
	req := raft.AppendRequest{Term: 5, PrevIndex: 6, PrevTerm: 3,
		Entries: []raft.Entry{{7, 3, "b"}}, LeaderCommit: 7}
	one, term, first := raft.Reconcile(base(), 5, req)
	two, term2, second := raft.Reconcile(one, term, req)
	if !reflect.DeepEqual(one, two) || term != term2 || first != second || len(two.Entries) != 3 {
		t.Fatalf("not idempotent: %#v %#v", one, two)
	}
}
