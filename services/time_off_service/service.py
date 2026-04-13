"""Time-off management service."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.persistence import get_db_session
from services.persistence.models import Member, TimeOff


def _time_off_to_dict(t: TimeOff, member_name: Optional[str] = None) -> Dict[str, Any]:
    return {
        "id": t.id,
        "member_id": t.member_id,
        "member_display_name": member_name or "",
        "leave_type": t.leave_type,
        "start_date": t.start_date,
        "end_date": t.end_date,
        "note": t.note,
    }


class TimeOffService:
    def list_time_offs(
        self,
        member_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with get_db_session() as session:
            q = session.query(TimeOff).join(Member, Member.id == TimeOff.member_id)
            if member_id is not None:
                q = q.filter(TimeOff.member_id == member_id)
            if start_date is not None:
                q = q.filter(TimeOff.end_date >= start_date)
            if end_date is not None:
                q = q.filter(TimeOff.start_date <= end_date)
            entries = q.order_by(TimeOff.start_date).all()
            # Build member name map
            member_map = {m.id: m.display_name for m in session.query(Member).all()}
            return [_time_off_to_dict(t, member_map.get(t.member_id, "")) for t in entries]

    def get_time_off(self, time_off_id: int) -> Optional[Dict[str, Any]]:
        with get_db_session() as session:
            t = session.query(TimeOff).filter_by(id=time_off_id).first()
            if t is None:
                return None
            member = session.query(Member).filter_by(id=t.member_id).first()
            return _time_off_to_dict(t, member.display_name if member else None)

    def create_time_off(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with get_db_session() as session:
            entry = TimeOff(
                member_id=data["member_id"],
                leave_type=data.get("leave_type", "annual"),
                start_date=data["start_date"],
                end_date=data["end_date"],
                note=data.get("note"),
            )
            session.add(entry)
            session.flush()
            member = session.query(Member).filter_by(id=entry.member_id).first()
            return _time_off_to_dict(entry, member.display_name if member else None)

    def update_time_off(self, time_off_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with get_db_session() as session:
            t = session.query(TimeOff).filter_by(id=time_off_id).first()
            if t is None:
                return None
            for field in ("leave_type", "start_date", "end_date", "note"):
                if field in data:
                    setattr(t, field, data[field])
            session.flush()
            member = session.query(Member).filter_by(id=t.member_id).first()
            return _time_off_to_dict(t, member.display_name if member else None)

    def delete_time_off(self, time_off_id: int) -> bool:
        with get_db_session() as session:
            t = session.query(TimeOff).filter_by(id=time_off_id).first()
            if t is None:
                return False
            session.delete(t)
            return True

    def get_summary_by_member(self, member_id: int) -> Dict[str, Any]:
        """Return total days taken per leave type for a member."""
        with get_db_session() as session:
            entries = session.query(TimeOff).filter_by(member_id=member_id).all()
            from datetime import date
            summary: Dict[str, int] = {}
            for t in entries:
                start = date.fromisoformat(t.start_date)
                end = date.fromisoformat(t.end_date)
                days = (end - start).days + 1
                summary[t.leave_type] = summary.get(t.leave_type, 0) + days
            return summary
