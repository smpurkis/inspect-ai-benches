// BUGGY STARTER: validates too late and grows through neighbors without realigning.
pub fn resize(
    comptime PoolType: type,
    pool: *PoolType,
    old: PoolType.Allocation,
    new_len: usize,
    new_alignment: usize,
) PoolType.Error!?PoolType.Allocation {
    const block = try pool.validate(old);
    if (new_len == 0) {
        try pool.free(old);
        return null;
    }

    block.len = new_len;
    block.alignment = new_alignment;
    return .{
        .slot = old.slot,
        .generation = old.generation,
        .offset = old.offset,
        .len = new_len,
        .alignment = new_alignment,
    };
}
