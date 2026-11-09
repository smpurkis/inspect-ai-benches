const std = @import("std");
const types = @import("pool.zig");

fn number(token: []const u8) !usize {
    return std.fmt.parseUnsigned(usize, token, 10);
}

fn handle(tokens: *std.mem.TokenIterator(u8, .scalar)) !types.Allocation {
    return .{
        .slot = @intCast(try number(tokens.next() orelse return error.BadCommand)),
        .generation = @intCast(try number(tokens.next() orelse return error.BadCommand)),
        .offset = try number(tokens.next() orelse return error.BadCommand),
        .len = try number(tokens.next() orelse return error.BadCommand),
        .alignment = try number(tokens.next() orelse return error.BadCommand),
    };
}

fn printAllocation(writer: anytype, allocation: types.Allocation) !void {
    try writer.print("ok {d} {d} {d} {d} {d}\n", .{
        allocation.slot, allocation.generation, allocation.offset,
        allocation.len, allocation.alignment,
    });
}

pub fn main() !void {
    var pool = types.Pool{};
    var input = std.io.bufferedReader(std.io.getStdIn().reader());
    var output = std.io.bufferedWriter(std.io.getStdOut().writer());
    const reader = input.reader();
    const writer = output.writer();
    var buffer: [4096]u8 = undefined;

    while (try reader.readUntilDelimiterOrEof(&buffer, '\n')) |line| {
        var tokens = std.mem.tokenizeScalar(u8, line, ' ');
        const command = tokens.next() orelse continue;
        if (std.mem.eql(u8, command, "alloc")) {
            const len = number(tokens.next() orelse "") catch {
                try writer.writeAll("err BadCommand\n"); continue;
            };
            const alignment = number(tokens.next() orelse "") catch {
                try writer.writeAll("err BadCommand\n"); continue;
            };
            const fill: u8 = @intCast((number(tokens.next() orelse "") catch 0) & 255);
            if (pool.allocate(len, alignment)) |allocation| {
                @memset(try pool.bytes(allocation), fill);
                try printAllocation(writer, allocation);
            } else |err| try writer.print("err {s}\n", .{@errorName(err)});
        } else if (std.mem.eql(u8, command, "resize")) {
            const old = handle(&tokens) catch {
                try writer.writeAll("err BadCommand\n"); continue;
            };
            const new_len = number(tokens.next() orelse "") catch {
                try writer.writeAll("err BadCommand\n"); continue;
            };
            const alignment = number(tokens.next() orelse "") catch {
                try writer.writeAll("err BadCommand\n"); continue;
            };
            if (pool.resize(old, new_len, alignment)) |maybe| {
                if (maybe) |allocation| try printAllocation(writer, allocation)
                else try writer.writeAll("nil\n");
            } else |err| try writer.print("err {s}\n", .{@errorName(err)});
        } else if (std.mem.eql(u8, command, "free")) {
            const allocation = handle(&tokens) catch {
                try writer.writeAll("err BadCommand\n"); continue;
            };
            if (pool.free(allocation)) |_| try writer.writeAll("ok\n")
            else |err| try writer.print("err {s}\n", .{@errorName(err)});
        } else if (std.mem.eql(u8, command, "check")) {
            const allocation = handle(&tokens) catch {
                try writer.writeAll("err BadCommand\n"); continue;
            };
            const count = number(tokens.next() orelse "") catch {
                try writer.writeAll("err BadCommand\n"); continue;
            };
            const expected: u8 = @intCast((number(tokens.next() orelse "") catch 0) & 255);
            if (pool.bytesConst(allocation)) |bytes| {
                if (count > bytes.len) {
                    try writer.writeAll("err Bounds\n");
                } else {
                    var good = true;
                    for (bytes[0..count]) |byte| good = good and byte == expected;
                    try writer.writeAll(if (good) "ok\n" else "mismatch\n");
                }
            } else |err| try writer.print("err {s}\n", .{@errorName(err)});
        } else {
            try writer.writeAll("err BadCommand\n");
        }
    }
    try output.flush();
}
