import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Action } from "../api/types";

/**
 * Subscribes to the session's Server-Sent Events stream while the agent is running.
 * EventSource reconnects on its own and sends Last-Event-ID, so no events are lost.
 * Calls `onEnd` once the backend reports the run has finished.
 */
export function useSessionEvents(sessionId: string, initial: Action[], live: boolean, onEnd: () => void): Action[] {
  const [actions, setActions] = useState<Action[]>(initial);

  useEffect(() => setActions(initial), [initial]);

  useEffect(() => {
    if (!live) return;
    const source = new EventSource(api.eventsUrl(sessionId));
    source.addEventListener("action", (event) => {
      const action: Action = JSON.parse((event as MessageEvent).data);
      setActions((current) => (current.some((a) => a.seq === action.seq) ? current : [...current, action]));
    });
    source.addEventListener("end", () => {
      source.close();
      onEnd();
    });
    return () => source.close();
  }, [sessionId, live, onEnd]);

  return actions;
}
