fn rangeIsFree(comptime PoolType: type, pool: *PoolType, old: PoolType.Allocation, new_len: usize) PoolType.Error!bool {
    if (old.offset > PoolType.capacity or new_len > PoolType.capacity - old.offset)
        return error.Overflow;
    const new_end = old.offset + new_len;
    for (pool.blocks, 0..) |other, index| {
        if (!other.active or index == old.slot) continue;
        const other_end = other.offset + other.len;
        if (old.offset < other_end and other.offset < new_end) return false;
    }
    return true;
}

pub fn resize(
    comptime PoolType: type,
    pool: *PoolType,
    old: PoolType.Allocation,
    new_len: usize,
    new_alignment: usize,
) PoolType.Error!?PoolType.Allocation {
    const block = try pool.validate(old);
    if (new_alignment == 0 or new_alignment > PoolType.max_alignment or
        (new_alignment & (new_alignment - 1)) != 0)
        return error.InvalidAlignment;
    if (new_len == 0) {
        try pool.free(old);
        return null;
    }

    if ((old.offset & (new_alignment - 1)) == 0 and
        (new_len <= old.len or try rangeIsFree(PoolType, pool, old, new_len)))
    {
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

    const replacement = try pool.allocate(new_len, new_alignment);
    const copy_len = @min(old.len, new_len);
    @memcpy((try pool.bytes(replacement))[0..copy_len], (try pool.bytesConst(old))[0..copy_len]);
    try pool.free(old);
    return replacement;
}
