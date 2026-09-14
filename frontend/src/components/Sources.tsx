interface SourcesProps {
  sources: string[];
  unresolvedGaps: string[];
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

/** 来源编号列表 + 未解决缺口提示。 */
export function Sources({ sources, unresolvedGaps }: SourcesProps) {
  return (
    <section className="sources-block">
      <div className="block-label">来源（{sources.length}）</div>
      {sources.length === 0 ? (
        <div className="sources-empty">（无成功抓取来源）</div>
      ) : (
        <ol className="sources">
          {sources.map((url, index) => (
            <li key={`${index}-${url}`}>
              <a href={url} target="_blank" rel="noreferrer">
                <span className="source-index">{index + 1}</span>
                <span className="source-host">{hostOf(url)}</span>
                <span className="source-url">{url}</span>
              </a>
            </li>
          ))}
        </ol>
      )}
      {unresolvedGaps.length > 0 && (
        <div className="gaps">
          <div className="gaps-label">未解决的研究缺口</div>
          <ul>
            {unresolvedGaps.map((gap, index) => (
              <li key={index}>{gap}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
