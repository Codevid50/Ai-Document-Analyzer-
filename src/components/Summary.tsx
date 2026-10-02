interface SummaryProps {
  summary: string;
  keyPoints: string[];
  keyTakeaways: string[];
}

export default function Summary({
  summary,
  keyPoints,
  keyTakeaways,
}: SummaryProps) {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-gray-900">Summary</h3>
        <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-gray-700">
          {summary}
        </p>
      </div>

      {keyPoints.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold text-gray-900">Key Points</h3>
          <ul className="mt-2 space-y-2">
            {keyPoints.map((point, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-blue-600" />
                {point}
              </li>
            ))}
          </ul>
        </div>
      )}

      {keyTakeaways.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold text-gray-900">Key Takeaways</h3>
          <ul className="mt-2 space-y-2">
            {keyTakeaways.map((takeaway, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-green-600" />
                {takeaway}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
