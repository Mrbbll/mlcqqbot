"""SQLite 投票状态存储。"""
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from config import POLL_DB_PATH


class PollStoreError(RuntimeError):
    """投票状态或候选项无效。"""


@dataclass(frozen=True)
class PollResult:
    """一轮投票的汇总结果。"""

    poll_id: int
    category: str
    total_votes: int
    candidates: tuple[tuple[int, str, int], ...]


@dataclass(frozen=True)
class VoteChange:
    """一次点击对选票造成的变化。"""

    candidate_name: str
    selected: bool


@dataclass(frozen=True)
class VoteSubmission:
    candidate_names: tuple[str, ...]


def _utc_now() -> str:
    """返回供 SQLite 存储的 UTC ISO 时间戳。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect(db_path: Path | str = POLL_DB_PATH) -> sqlite3.Connection:
    """连接投票数据库并确保所需表结构已初始化。"""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS polls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_openid TEXT NOT NULL,
            category TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'closed')),
            created_at TEXT NOT NULL,
            closed_at TEXT
        );

        CREATE UNIQUE INDEX IF NOT EXISTS one_active_poll_per_group
        ON polls(group_openid)
        WHERE status = 'active';

        CREATE TABLE IF NOT EXISTS poll_candidates (
            poll_id INTEGER NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
            candidate_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            PRIMARY KEY (poll_id, candidate_id)
        );

        """
    )
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS poll_votes (
            poll_id INTEGER NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
            voter_openid TEXT NOT NULL,
            candidate_id INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (poll_id, voter_openid, candidate_id),
            FOREIGN KEY (poll_id, candidate_id)
                REFERENCES poll_candidates(poll_id, candidate_id)
        );
        CREATE TABLE IF NOT EXISTS poll_drafts (
            poll_id INTEGER NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
            voter_openid TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (poll_id, voter_openid)
        );
        CREATE TABLE IF NOT EXISTS poll_selections (
            poll_id INTEGER NOT NULL,
            voter_openid TEXT NOT NULL,
            candidate_id INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (poll_id, voter_openid, candidate_id),
            FOREIGN KEY (poll_id, candidate_id)
                REFERENCES poll_candidates(poll_id, candidate_id)
                ON DELETE CASCADE
        );
        """
    )
    connection.commit()
    return connection


@contextmanager
def _database(db_path: Path | str = POLL_DB_PATH):
    """提交或回滚事务，并确保 Windows 上及时释放数据库文件句柄。"""
    connection = _connect(db_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def start_poll(
    group_openid: str,
    category: str,
    candidates: Sequence[str],
    *,
    db_path: Path | str = POLL_DB_PATH,
) -> int:
    """关闭群内旧投票并创建新投票，返回投票 ID。"""
    cleaned = tuple(name.strip() for name in candidates if name.strip())
    if not group_openid:
        raise PollStoreError("缺少群聊标识")
    if not cleaned:
        raise PollStoreError("候选项为空")

    now = _utc_now()
    with _database(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            UPDATE polls
            SET status = 'closed', closed_at = ?
            WHERE group_openid = ? AND status = 'active'
            """,
            (now, group_openid),
        )
        cursor = connection.execute(
            """
            INSERT INTO polls(group_openid, category, status, created_at)
            VALUES (?, ?, 'active', ?)
            """,
            (group_openid, category, now),
        )
        poll_id = int(cursor.lastrowid)
        connection.executemany(
            """
            INSERT INTO poll_candidates(poll_id, candidate_id, name)
            VALUES (?, ?, ?)
            """,
            (
                (poll_id, candidate_id, name)
                for candidate_id, name in enumerate(cleaned, start=1)
            ),
        )
    return poll_id


def close_poll(
    poll_id: int,
    *,
    db_path: Path | str = POLL_DB_PATH,
) -> None:
    """关闭指定投票，供消息发送失败时回滚活动状态。"""
    with _database(db_path) as connection:
        connection.execute(
            """
            UPDATE polls
            SET status = 'closed', closed_at = ?
            WHERE id = ? AND status = 'active'
            """,
            (_utc_now(), poll_id),
        )


def toggle_vote_selection(
    group_openid: str,
    poll_id: int,
    voter_openid: str,
    candidate_id: int,
    *,
    db_path: Path | str = POLL_DB_PATH,
) -> VoteChange:
    """切换一名群成员对候选项的选中状态。"""
    if not voter_openid:
        raise PollStoreError("缺少投票成员标识")

    with _database(db_path) as connection:
        # 将“仍为活动投票”的校验和改票写入放在同一写事务中，避免并发开新投票时误收旧票。
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT poll_candidates.name
            FROM polls
            JOIN poll_candidates ON poll_candidates.poll_id = polls.id
            WHERE polls.id = ?
              AND polls.group_openid = ?
              AND polls.status = 'active'
              AND poll_candidates.candidate_id = ?
            """,
            (poll_id, group_openid, candidate_id),
        ).fetchone()
        if row is None:
            raise PollStoreError("投票已结束或候选项不存在")

        draft_insert = connection.execute(
            "INSERT OR IGNORE INTO poll_drafts(poll_id, voter_openid, updated_at) VALUES (?, ?, ?)",
            (poll_id, voter_openid, _utc_now()),
        )
        if draft_insert.rowcount:
            connection.execute(
                """
                INSERT OR IGNORE INTO poll_selections(
                    poll_id, voter_openid, candidate_id, updated_at
                )
                SELECT poll_id, voter_openid, candidate_id, ?
                FROM poll_votes
                WHERE poll_id = ? AND voter_openid = ?
                """,
                (_utc_now(), poll_id, voter_openid),
            )
        existing = connection.execute(
            """
            SELECT 1 FROM poll_selections
            WHERE poll_id = ? AND voter_openid = ? AND candidate_id = ?
            """,
            (poll_id, voter_openid, candidate_id),
        ).fetchone()
        if existing is None:
            connection.execute(
                """
                INSERT INTO poll_selections(
                    poll_id, voter_openid, candidate_id, updated_at
                ) VALUES (?, ?, ?, ?)
                """,
                (poll_id, voter_openid, candidate_id, _utc_now()),
            )
            selected = True
        else:
            connection.execute(
                """
                DELETE FROM poll_selections
                WHERE poll_id = ? AND voter_openid = ? AND candidate_id = ?
                """,
                (poll_id, voter_openid, candidate_id),
            )
            selected = False
    return VoteChange(candidate_name=str(row[0]), selected=selected)


def submit_vote(
    group_openid: str,
    poll_id: int,
    voter_openid: str,
    *,
    db_path: Path | str = POLL_DB_PATH,
) -> VoteSubmission:
    """将用户当前草稿原子提交为正式投票。"""
    if not voter_openid:
        raise PollStoreError("缺少投票成员标识")
    with _database(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        active = connection.execute(
            "SELECT 1 FROM polls WHERE id = ? AND group_openid = ? AND status = 'active'",
            (poll_id, group_openid),
        ).fetchone()
        if active is None:
            raise PollStoreError("投票已结束或不存在")
        draft = connection.execute(
            "SELECT 1 FROM poll_drafts WHERE poll_id = ? AND voter_openid = ?",
            (poll_id, voter_openid),
        ).fetchone()
        if draft is None:
            raise PollStoreError("未检测到待提交的选择")
        rows = connection.execute(
            """
            SELECT c.name
            FROM poll_selections s
            JOIN poll_candidates c
              ON c.poll_id = s.poll_id AND c.candidate_id = s.candidate_id
            WHERE s.poll_id = ? AND s.voter_openid = ?
            ORDER BY s.candidate_id
            """,
            (poll_id, voter_openid),
        ).fetchall()
        names = tuple(str(row[0]) for row in rows)
        connection.execute(
            "DELETE FROM poll_votes WHERE poll_id = ? AND voter_openid = ?",
            (poll_id, voter_openid),
        )
        connection.execute(
            """
            INSERT INTO poll_votes(poll_id, voter_openid, candidate_id, updated_at)
            SELECT poll_id, voter_openid, candidate_id, ?
            FROM poll_selections
            WHERE poll_id = ? AND voter_openid = ?
            """,
            (_utc_now(), poll_id, voter_openid),
        )
        connection.execute(
            "DELETE FROM poll_selections WHERE poll_id = ? AND voter_openid = ?",
            (poll_id, voter_openid),
        )
        connection.execute(
            "DELETE FROM poll_drafts WHERE poll_id = ? AND voter_openid = ?",
            (poll_id, voter_openid),
        )
    return VoteSubmission(candidate_names=names)


def get_active_poll_result(
    group_openid: str,
    *,
    db_path: Path | str = POLL_DB_PATH,
) -> PollResult | None:
    """读取群内当前活动投票的候选项及票数。"""
    with _database(db_path) as connection:
        poll = connection.execute(
            """
            SELECT id, category
            FROM polls
            WHERE group_openid = ? AND status = 'active'
            """,
            (group_openid,),
        ).fetchone()
        if poll is None:
            return None

        poll_id, category = int(poll[0]), str(poll[1])
        rows = connection.execute(
            """
            SELECT
                poll_candidates.candidate_id,
                poll_candidates.name,
                COUNT(poll_votes.voter_openid) AS vote_count
            FROM poll_candidates
            LEFT JOIN poll_votes
              ON poll_votes.poll_id = poll_candidates.poll_id
             AND poll_votes.candidate_id = poll_candidates.candidate_id
            WHERE poll_candidates.poll_id = ?
            GROUP BY poll_candidates.candidate_id, poll_candidates.name
            ORDER BY poll_candidates.candidate_id
            """,
            (poll_id,),
        ).fetchall()

    candidates = tuple(
        (int(candidate_id), str(name), int(vote_count))
        for candidate_id, name, vote_count in rows
    )
    return PollResult(
        poll_id=poll_id,
        category=category,
        total_votes=sum(item[2] for item in candidates),
        candidates=candidates,
    )
