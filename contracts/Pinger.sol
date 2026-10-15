// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// arc-pulse: on-chain pings to measure the Arc network.
/// Each ping stores (sentAtMs, blockNumber, blockTimestamp, prevLatencyMs) in a 32-slot ring buffer,
/// so a static page can read the latest pings with one eth_call (no log-range queries).
contract Pinger {
    struct P {
        uint64 sentAtMs;     // client clock when the tx was signed, ms
        uint64 blockNumber;  // block that included the ping
        uint64 ts;           // block.timestamp, s (Arc blocks are ~0.5 s, so this is coarse)
        uint32 prevLatencyMs; // send→receipt latency of the PREVIOUS ping, measured by the pinger
    }

    address public immutable owner;
    uint256 public seq;
    P[32] private ring;

    event Ping(uint256 indexed seq, uint64 sentAtMs, uint64 ts, uint32 prevLatencyMs);

    constructor() {
        owner = msg.sender;
    }

    function ping(uint64 sentAtMs, uint32 prevLatencyMs) external {
        require(msg.sender == owner, "owner only");
        unchecked { seq++; }
        ring[seq % 32] = P(sentAtMs, uint64(block.number), uint64(block.timestamp), prevLatencyMs);
        emit Ping(seq, sentAtMs, uint64(block.timestamp), prevLatencyMs);
    }

    /// Latest pings, newest first (up to 32), and the total count.
    function recent() external view returns (P[] memory out, uint256 total) {
        total = seq;
        uint256 n = total < 32 ? total : 32;
        out = new P[](n);
        for (uint256 i = 0; i < n; i++) {
            out[i] = ring[(total - i) % 32];
        }
    }
}
