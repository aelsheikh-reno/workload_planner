export function ScreenHeader({ eyebrow, title, description, actions }) {
  return (
    <header className="screen-header">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h2>{title}</h2>
        {description ? <p className="supporting-text">{description}</p> : null}
      </div>
      {actions ? <div className="screen-header__actions">{actions}</div> : null}
    </header>
  );
}

export function ScreenStateCard({ state, message, tone = "muted" }) {
  return (
    <div className={`state-card state-card--${tone}`}>
      <strong>{state}</strong>
      <p>{message}</p>
    </div>
  );
}

export function ErrorCard({ error, retryLabel = "Try again", onRetry }) {
  return (
    <div className="state-card state-card--bad" role="alert">
      <strong>{error?.code || "request_failed"}</strong>
      <p>{error?.message || "The request could not be completed."}</p>
      {onRetry ? (
        <button className="secondary-button" onClick={onRetry} type="button">
          {retryLabel}
        </button>
      ) : null}
    </div>
  );
}

export function MetricGrid({ items }) {
  return (
    <div className="metric-grid">
      {items.map((item) => (
        <article className="metric-card" key={item.label}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
          {item.caption ? <small>{item.caption}</small> : null}
        </article>
      ))}
    </div>
  );
}

export function SectionCard({ title, subtitle, actions, children }) {
  return (
    <section className="panel">
      <div className="panel__header">
        <div>
          <h3>{title}</h3>
          {subtitle ? <p className="supporting-text">{subtitle}</p> : null}
        </div>
        {actions ? <div className="panel__actions">{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}

export function LoadingSkeleton({ label }) {
  return (
    <div className="state-card state-card--muted" role="status">
      <strong>Loading</strong>
      <p>{label}</p>
    </div>
  );
}
