const std = @import("std");
const kernel = @import("aligned_pool.zig");

const pool_capacity: usize = 131072;
pub const capacity = pool_capacity;
pub const max_blocks: usize = 128;
const pool_max_alignment: usize = 4096;
pub const max_alignment = pool_max_alignment;

const PoolError = error{
    InvalidAlignment,
    InvalidHandle,
    OutOfMemory,
    Overflow,
};

const AllocationHandle = struct {
    slot: u16,
    generation: u32,
    offset: usize,
    len: usize,
    alignment: usize,
};

pub const Error = PoolError;
pub const Allocation = AllocationHandle;

pub const Block = struct {
    active: bool = false,
    generation: u32 = 1,
    offset: usize = 0,
    len: usize = 0,
    alignment: usize = 1,
};

pub const Pool = struct {
    pub const Error = PoolError;
    pub const Allocation = AllocationHandle;
    pub const capacity = pool_capacity;
    pub const max_alignment = pool_max_alignment;

    backing: [pool_capacity]u8 = [_]u8{0} ** pool_capacity,
    blocks: [max_blocks]Block = [_]Block{.{}} ** max_blocks,

    pub fn validate(self: *Pool, allocation: AllocationHandle) PoolError!*Block {
        if (allocation.slot >= max_blocks) return error.InvalidHandle;
        const block = &self.blocks[allocation.slot];
        if (!block.active or block.generation != allocation.generation or
            block.offset != allocation.offset or block.len != allocation.len or
            block.alignment != allocation.alignment)
            return error.InvalidHandle;
        return block;
    }

    pub fn allocate(self: *Pool, len: usize, alignment: usize) PoolError!AllocationHandle {
        if (alignment == 0 or alignment > pool_max_alignment or !std.math.isPowerOfTwo(alignment))
            return error.InvalidAlignment;
        if (len == 0) return error.OutOfMemory;

        var slot: ?usize = null;
        for (&self.blocks, 0..) |*block, index| {
            if (!block.active) {
                slot = index;
                break;
            }
        }
        const selected = slot orelse return error.OutOfMemory;

        var cursor: usize = 0;
        while (true) {
            const padding = (0 -% cursor) & (alignment - 1);
            const start = std.math.add(usize, cursor, padding) catch return error.Overflow;
            const end = std.math.add(usize, start, len) catch return error.Overflow;
            if (end > pool_capacity) return error.OutOfMemory;

            var next_cursor: ?usize = null;
            for (self.blocks) |block| {
                if (!block.active) continue;
                const block_end = block.offset + block.len;
                if (start < block_end and block.offset < end) {
                    next_cursor = @max(next_cursor orelse 0, block_end);
                }
            }
            if (next_cursor) |next| {
                cursor = next;
                continue;
            }

            const block = &self.blocks[selected];
            block.active = true;
            block.offset = start;
            block.len = len;
            block.alignment = alignment;
            return .{
                .slot = @intCast(selected),
                .generation = block.generation,
                .offset = start,
                .len = len,
                .alignment = alignment,
            };
        }
    }

    pub fn free(self: *Pool, allocation: AllocationHandle) PoolError!void {
        const block = try self.validate(allocation);
        block.active = false;
        block.offset = 0;
        block.len = 0;
        block.alignment = 1;
        block.generation +%= 1;
        if (block.generation == 0) block.generation = 1;
    }

    pub fn bytes(self: *Pool, allocation: AllocationHandle) PoolError![]u8 {
        _ = try self.validate(allocation);
        return self.backing[allocation.offset .. allocation.offset + allocation.len];
    }

    pub fn bytesConst(self: *Pool, allocation: AllocationHandle) PoolError![]const u8 {
        return try self.bytes(allocation);
    }

    pub fn resize(self: *Pool, old: AllocationHandle, new_len: usize, new_alignment: usize) PoolError!?AllocationHandle {
        return kernel.resize(Pool, self, old, new_len, new_alignment);
    }
};
