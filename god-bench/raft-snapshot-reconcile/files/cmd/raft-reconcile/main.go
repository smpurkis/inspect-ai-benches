package main

import (
	"encoding/json"
	"fmt"
	"os"

	"raftsnapshot/raft"
)

type input struct {
	State raft.State
	CurrentTerm uint64
	Request raft.AppendRequest
}

func main() {
	var in input
	if err := json.NewDecoder(os.Stdin).Decode(&in); err != nil { panic(err) }
	state, term, result := raft.Reconcile(in.State, in.CurrentTerm, in.Request)
	if err := json.NewEncoder(os.Stdout).Encode(struct {
		State raft.State
		CurrentTerm uint64
		Result raft.AppendResult
	}{state, term, result}); err != nil { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
}
