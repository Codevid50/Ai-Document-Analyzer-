"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, getApiErrorMessage, getStoredToken } from "@/lib/api";

interface AdminUser {
  id: number;
  email: string;
  created_at: string;
  last_login_at: string | null;
  is_active: boolean;
  document_count: number;
}

interface LoginEvent {
  id: number;
  email: string;
  success: boolean;
  created_at: string;
}

interface CurrentUser {
  id: number;
  is_admin: boolean;
}

class AdminApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function fetchAdminData<T>(path: string, fallback: string): Promise<T> {
  const response = await apiFetch(path);
  if (!response.ok) {
    throw new AdminApiError(
      await getApiErrorMessage(response, fallback),
      response.status,
    );
  }
  return response.json() as Promise<T>;
}

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "Never";
}

export default function AdminPage() {
  const router = useRouter();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loginEvents, setLoginEvents] = useState<LoginEvent[]>([]);
  const [adminId, setAdminId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [updatingUserId, setUpdatingUserId] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const [userList, eventList] = await Promise.all([
        fetchAdminData<AdminUser[]>(
          "/admin/users",
          "Failed to load users.",
        ),
        fetchAdminData<LoginEvent[]>(
          "/admin/login-events?limit=100",
          "Failed to load login attempts.",
        ),
      ]);
      setUsers(userList);
      setLoginEvents(eventList);
    } catch (requestError: unknown) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to load administrator data.",
      );
      if (
        requestError instanceof AdminApiError &&
        (requestError.status === 401 || requestError.status === 403)
      ) {
        router.replace("/");
      }
    } finally {
      setIsLoading(false);
    }
  }, [router]);

  useEffect(() => {
    let isCurrent = true;
    const authorize = async () => {
      if (!getStoredToken()) {
        router.replace("/");
        return;
      }

      try {
        const currentUser = await fetchAdminData<CurrentUser>(
          "/auth/me",
          "Unable to verify administrator access.",
        );
        if (!isCurrent) return;
        if (!currentUser.is_admin) {
          router.replace("/");
          return;
        }
        setAdminId(currentUser.id);
        await refresh();
      } catch (requestError: unknown) {
        if (isCurrent) {
          if (
            requestError instanceof AdminApiError &&
            (requestError.status === 401 || requestError.status === 403)
          ) {
            router.replace("/");
            return;
          }
          setError(
            requestError instanceof Error
              ? requestError.message
              : "Unable to verify administrator access.",
          );
          setIsLoading(false);
        }
      }
    };

    void authorize();
    return () => {
      isCurrent = false;
    };
  }, [refresh, router]);

  const toggleUser = async (user: AdminUser) => {
    const nextIsActive = !user.is_active;
    const action = nextIsActive ? "enable" : "disable";
    if (
      !window.confirm(
        `Are you sure you want to ${action} ${user.email}?`,
      )
    ) {
      return;
    }

    setUpdatingUserId(user.id);
    setError("");
    try {
      const response = await apiFetch(`/admin/users/${user.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: nextIsActive }),
      });
      if (!response.ok) {
        throw new Error(
          await getApiErrorMessage(response, `Failed to ${action} this user.`),
        );
      }
      await refresh();
    } catch (requestError: unknown) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : `Failed to ${action} this user.`,
      );
    } finally {
      setUpdatingUserId(null);
    }
  };

  return (
    <main className="min-h-screen bg-gray-50 px-4 py-8 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-6xl">
        <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
          <div>
            <Link
              href="/"
              className="text-sm font-medium text-blue-600 hover:text-blue-700"
            >
              Back to documents
            </Link>
            <h1 className="mt-2 text-3xl font-bold text-gray-900">
              Admin
            </h1>
          </div>
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={isLoading}
            className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isLoading ? "Loading..." : "Refresh"}
          </button>
        </header>

        {error && (
          <div
            role="alert"
            className="mb-6 rounded-md bg-red-50 p-4 text-sm text-red-700"
          >
            {error}
          </div>
        )}

        {isLoading && users.length === 0 && loginEvents.length === 0 ? (
          <p className="text-sm text-gray-500">Loading admin data...</p>
        ) : (
          <div className="space-y-8">
            <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
              <h2 className="mb-4 text-xl font-semibold text-gray-900">
                Users
              </h2>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] text-left text-sm">
                  <thead className="border-b border-gray-200 text-gray-500">
                    <tr>
                      <th className="px-3 py-3 font-medium">Email</th>
                      <th className="px-3 py-3 font-medium">Created</th>
                      <th className="px-3 py-3 font-medium">Last login</th>
                      <th className="px-3 py-3 font-medium">Documents</th>
                      <th className="px-3 py-3 font-medium">Status</th>
                      <th className="px-3 py-3 font-medium">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {users.map((user) => (
                      <tr key={user.id}>
                        <td className="px-3 py-3 text-gray-900">
                          {user.email}
                        </td>
                        <td className="px-3 py-3 text-gray-600">
                          {formatDate(user.created_at)}
                        </td>
                        <td className="px-3 py-3 text-gray-600">
                          {formatDate(user.last_login_at)}
                        </td>
                        <td className="px-3 py-3 text-gray-600">
                          {user.document_count}
                        </td>
                        <td className="px-3 py-3">
                          <span
                            className={
                              user.is_active
                                ? "text-green-700"
                                : "text-gray-500"
                            }
                          >
                            {user.is_active ? "Enabled" : "Disabled"}
                          </span>
                        </td>
                        <td className="px-3 py-3">
                          <button
                            type="button"
                            onClick={() => void toggleUser(user)}
                            disabled={
                              updatingUserId !== null ||
                              user.id === adminId
                            }
                            title={
                              user.id === adminId
                                ? "You cannot change your own account status."
                                : undefined
                            }
                            className="rounded-md border border-gray-300 px-3 py-1.5 font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {updatingUserId === user.id
                              ? "Saving..."
                              : user.is_active
                                ? "Disable"
                                : "Enable"}
                          </button>
                        </td>
                      </tr>
                    ))}
                    {users.length === 0 && (
                      <tr>
                        <td
                          colSpan={6}
                          className="px-3 py-6 text-center text-gray-500"
                        >
                          No users found.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
              <h2 className="mb-4 text-xl font-semibold text-gray-900">
                Recent login attempts
              </h2>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[520px] text-left text-sm">
                  <thead className="border-b border-gray-200 text-gray-500">
                    <tr>
                      <th className="px-3 py-3 font-medium">Result</th>
                      <th className="px-3 py-3 font-medium">Email</th>
                      <th className="px-3 py-3 font-medium">Time</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {loginEvents.map((event) => (
                      <tr key={event.id}>
                        <td
                          className={`px-3 py-3 font-medium ${
                            event.success ? "text-green-700" : "text-red-700"
                          }`}
                        >
                          {event.success ? "Success" : "Failed"}
                        </td>
                        <td className="px-3 py-3 text-gray-900">
                          {event.email}
                        </td>
                        <td className="px-3 py-3 text-gray-600">
                          {formatDate(event.created_at)}
                        </td>
                      </tr>
                    ))}
                    {loginEvents.length === 0 && (
                      <tr>
                        <td
                          colSpan={3}
                          className="px-3 py-6 text-center text-gray-500"
                        >
                          No login attempts found.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        )}
      </div>
    </main>
  );
}
