// Holds the currently-selected user across all pages.
//
// Profile, routine, and scan personalisation all key off a single user_id, so
// it lives in one context and is persisted to localStorage to survive reloads.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api } from "../api/client";
import type { UserSummary } from "../api/types";

interface UserContextValue {
  users: UserSummary[];
  currentUserId: string | null;
  currentUser: UserSummary | null;
  loading: boolean;
  error: string | null;
  selectUser: (userId: string | null) => void;
  refreshUsers: () => Promise<void>;
}

const STORAGE_KEY = "skingraph.currentUserId";

const UserContext = createContext<UserContextValue | undefined>(undefined);

export function UserProvider({ children }: { children: ReactNode }) {
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [currentUserId, setCurrentUserId] = useState<string | null>(() =>
    localStorage.getItem(STORAGE_KEY),
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refreshUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await api.listUsers();
      setUsers(list);
      // Drop a stale selection (and its localStorage entry) if that user no
      // longer exists — e.g. after a delete from another tab.
      setCurrentUserId((prev) => {
        if (prev && !list.some((u) => u.user_id === prev)) {
          localStorage.removeItem(STORAGE_KEY);
          return null;
        }
        return prev;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshUsers();
  }, [refreshUsers]);

  const selectUser = useCallback((userId: string | null) => {
    setCurrentUserId(userId);
    if (userId) localStorage.setItem(STORAGE_KEY, userId);
    else localStorage.removeItem(STORAGE_KEY);
  }, []);

  const currentUser =
    users.find((u) => u.user_id === currentUserId) ?? null;

  return (
    <UserContext.Provider
      value={{
        users,
        currentUserId,
        currentUser,
        loading,
        error,
        selectUser,
        refreshUsers,
      }}
    >
      {children}
    </UserContext.Provider>
  );
}

export function useUsers(): UserContextValue {
  const ctx = useContext(UserContext);
  if (!ctx) throw new Error("useUsers must be used within a UserProvider");
  return ctx;
}
