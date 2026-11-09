package raft

// Reconcile applies one AppendEntries-style request to a follower value.
// The returned State must own its Entries backing array.
func Reconcile(state State, currentTerm uint64, req AppendRequest) (State, uint64, AppendResult) {
	// BUG: stale leaders are allowed to rewrite the follower.
	if req.Term > currentTerm {
		currentTerm = req.Term
	}

	// BUG: this offset calculation does not handle PrevIndex at or below a snapshot.
	offset := int(req.PrevIndex - state.Snapshot.Index)
	if offset < 0 || offset > len(state.Entries) {
		return state, currentTerm, AppendResult{}
	}
	if req.PrevIndex == state.Snapshot.Index {
		if req.PrevTerm != state.Snapshot.Term { return state, currentTerm, AppendResult{} }
	} else if state.Entries[offset-1].Term != req.PrevTerm {
		return state, currentTerm, AppendResult{}
	}

	// BUG: duplicate retries truncate an unmatched suffix and conflicts can erase commit.
	entries := append([]Entry(nil), state.Entries[:offset]...)
	entries = append(entries, req.Entries...)
	state.Entries = entries
	last := state.LastIndex()
	state.Commit = req.LeaderCommit
	if state.Commit > last { state.Commit = last }
	return state, currentTerm, AppendResult{Accepted: true, MatchIndex: last}
}
