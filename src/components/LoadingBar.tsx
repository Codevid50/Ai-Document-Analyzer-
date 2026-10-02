"use client";

interface LoadingBarProps {
  isLoading: boolean;
}

export default function LoadingBar({ isLoading }: LoadingBarProps) {
  if (!isLoading) return null;

  return (
    <div className="loading-bar">
      <div className="loading-bar-progress" />
    </div>
  );
}
