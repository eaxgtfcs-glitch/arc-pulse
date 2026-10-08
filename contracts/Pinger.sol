// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// Пинг-контракт arc-pulse: каждый ping() эмитит событие для замера сети.
contract Pinger {
    uint256 public seq;
    event Ping(address indexed sender, uint256 seq, uint256 ts);

    function ping() external {
        unchecked { seq++; }
        emit Ping(msg.sender, seq, block.timestamp);
    }
}
