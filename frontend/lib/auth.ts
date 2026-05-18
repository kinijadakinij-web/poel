export interface UserAccount {
  id: string;
  username: string;
  passkey: string;
  leverage: number;
  margin: number;
  balance: number;
  initialBalance: number;
  createdAt: number;
}

export interface UserSession {
  userId: string;
  username: string;
  token: string;
  expiresAt: number;
}

const USERS_KEY = "agent-x-users";
const SESSION_KEY = "agent-x-session";

export function getUsers(): UserAccount[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(USERS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function saveUser(user: UserAccount) {
  const users = getUsers().filter((u) => u.id !== user.id);
  users.push(user);
  localStorage.setItem(USERS_KEY, JSON.stringify(users));
}

export function getSession(): UserSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const session: UserSession = JSON.parse(raw);
    if (Date.now() > session.expiresAt) {
      localStorage.removeItem(SESSION_KEY);
      return null;
    }
    return session;
  } catch {
    return null;
  }
}

export function setSession(session: UserSession) {
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearSession() {
  localStorage.removeItem(SESSION_KEY);
}

export function validatePasskey(
  username: string,
  passkey: string
): UserAccount | null {
  const users = getUsers();
  return (
    users.find(
      (u) =>
        u.username.toLowerCase() === username.toLowerCase() &&
        u.passkey === passkey
    ) || null
  );
}

// Seed akun demo kalau belum ada (hapus kalau sudah production)
export function seedDefaultUser() {
  if (typeof window === "undefined") return;
  const users = getUsers();
  if (users.length === 0) {
    saveUser({
      id: "usr-demo",
      username: "demo",
      passkey: "demo123",
      leverage: 10,
      margin: 100,
      balance: 1000,
      initialBalance: 1000,
      createdAt: Date.now(),
    });
  }
}

// Ambil data user dari session
export function getCurrentUser(): UserAccount | null {
  const session = getSession();
  if (!session) return null;
  return getUsers().find((u) => u.id === session.userId) || null;
}

// Update data user
export function updateUserData(userId: string, patch: Partial<UserAccount>) {
  const users = getUsers();
  const idx = users.findIndex((u) => u.id === userId);
  if (idx === -1) return;
  users[idx] = { ...users[idx], ...patch };
  localStorage.setItem(USERS_KEY, JSON.stringify(users));
}
