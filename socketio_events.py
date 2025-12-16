# socketio_events.py
from flask import session, current_app, request
from flask_socketio import join_room
from datetime import datetime
from sqlalchemy import text
from extensions import socketio, db

def verify_token(token):
    """
    If you use JWT token for socket auth, verify here and return user_id.
    For now we return None to fall back to cookie session auth.
    """
    return None

@socketio.on('connect')
def on_connect():
    current_app.logger.info("Socket connected: sid=%s", request.sid)
    # client should emit 'authenticate' right after connect

@socketio.on('authenticate')
def on_auth(data):
    # client emits: socket.emit('authenticate', { token: TOKEN })
    token = (data or {}).get('token') if isinstance(data, dict) else None
    user_id = None

    if token:
        user_id = verify_token(token)

    if user_id is None:
        # fallback to flask session cookie
        try:
            user_id = session.get('user_id')
        except Exception:
            user_id = None

    if not user_id:
        socketio.emit('auth_error', {'error': 'unauthenticated'}, room=request.sid)
        current_app.logger.info("Socket auth failed for sid=%s", request.sid)
        return

    room = f"user_{user_id}"
    join_room(room)
    socketio.emit('auth_success', {'user_id': user_id}, room=request.sid)
    current_app.logger.info("User %s joined room %s (sid=%s)", user_id, room, request.sid)

@socketio.on('private_message')
def on_private_message(payload):
    """
    Payload: { recipient_id: int, content: str }
    We persist to the DB then emit to both recipient and sender rooms.
    """
    try:
        sender = session.get('user_id')
    except Exception:
        sender = None

    if not sender:
        socketio.emit('pm_error', {'error': 'unauthenticated'}, room=request.sid)
        return

    recipient = payload.get('recipient_id')
    content = payload.get('content')

    try:
        recipient = int(recipient)
    except Exception:
        socketio.emit('pm_error', {'error': 'invalid recipient'}, room=request.sid)
        return

    if not content or not str(content).strip():
        socketio.emit('pm_error', {'error': 'empty content'}, room=request.sid)
        return

    # persist message
    try:
        insert_sql = text(
            "INSERT INTO messages (sender_id, recipient_id, content, created_at) "
            "VALUES (:s, :r, :c, NOW())"
        )
        db.session.execute(insert_sql, {'s': sender, 'r': recipient, 'c': content})
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to save private message")
        socketio.emit('pm_error', {'error': 'db error'}, room=request.sid)
        return

    out_msg = {
        'sender_id': sender,
        'recipient_id': recipient,
        'content': content,
        'created_at': datetime.utcnow().isoformat()
    }

    # emit to recipient and ack to sender
    try:
        socketio.emit('new_direct_message', out_msg, room=f"user_{recipient}")
        socketio.emit('message_sent', out_msg, room=f"user_{sender}")
    except Exception:
        current_app.logger.exception("Failed to emit new_direct_message")

