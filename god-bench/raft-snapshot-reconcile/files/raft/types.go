package raft

import "fmt"

type Entry struct {
	Index uint64
	Term  uint64
	Data  string
}

type Snapshot struct {
	Index uint64
	Term  uint64
}

type State struct {
	Snapshot Snapshot
	Entries  []Entry
	Commit   uint64
}

type AppendRequest struct {
	Term         uint64
	PrevIndex    uint64
	PrevTerm     uint64
	Entries      []Entry
	LeaderCommit uint64
}

type AppendResult struct {
	Accepted   bool
	MatchIndex uint64
}

func (s State) LastIndex() uint64 {
	if len(s.Entries) == 0 { return s.Snapshot.Index }
	return s.Entries[len(s.Entries)-1].Index
}

func (s State) Validate() error {
	expected := s.Snapshot.Index + 1
	for _, entry := range s.Entries {
		if entry.Index != expected { return fmt.Errorf("entry index %d, want %d", entry.Index, expected) }
		expected++
	}
	if s.Commit < s.Snapshot.Index || s.Commit > s.LastIndex() {
		return fmt.Errorf("commit %d outside [%d,%d]", s.Commit, s.Snapshot.Index, s.LastIndex())
	}
	return nil
}
