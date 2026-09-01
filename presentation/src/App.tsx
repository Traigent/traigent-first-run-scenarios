import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { brandName, traigentLogoPngDataUri } from "./brand";
import { coreSlideCount, presentation } from "./content";
import {
  coverageLabel,
  displayEyebrow,
  evidenceLabel,
  type CatalogEntry,
  type SlideSpec,
} from "./model";

function initialSlideIndex(): number {
  const slideId = window.location.hash.replace(/^#\/?/, "");
  const index = presentation.slides.findIndex((slide) => slide.id === slideId);
  return index >= 0 ? index : 0;
}

function HighlightedTitle({ slide }: { slide: SlideSpec }) {
  if (slide.accent === undefined) {
    return <>{slide.title}</>;
  }
  const titleLower = slide.title.toLocaleLowerCase("en");
  const accentLower = slide.accent.toLocaleLowerCase("en");
  const start = titleLower.indexOf(accentLower);
  if (start < 0) {
    return <>{slide.title}</>;
  }
  const end = start + slide.accent.length;
  return (
    <>
      {slide.title.slice(0, start)}
      <span className="title-accent">{slide.title.slice(start, end)}</span>
      {slide.title.slice(end)}
    </>
  );
}

function EvidenceBadge({ slide }: { slide: SlideSpec }) {
  return (
    <span className={`evidence-badge evidence-${slide.evidenceState}`}>
      {evidenceLabel(slide.evidenceState)}
    </span>
  );
}

function Metrics({ slide }: { slide: SlideSpec }) {
  if (slide.metrics.length === 0) {
    return null;
  }
  return (
    <dl className="metric-grid" aria-label="Scenario metrics">
      {slide.metrics.map((metric) => (
        <div className={`metric-card tone-${metric.tone}`} key={metric.label}>
          <dt>{metric.label}</dt>
          <dd>{metric.value}</dd>
          <p>{metric.detail}</p>
        </div>
      ))}
    </dl>
  );
}

function Journey({ slide }: { slide: SlideSpec }) {
  if (slide.steps.length === 0) {
    return null;
  }
  return (
    <ol
      className={`journey journey-${slide.steps.length}`}
      aria-label="First-run journey"
    >
      {slide.steps.map((step, index) => (
        <li key={`${step.executor}-${step.label}`}>
          <div className="step-number" aria-hidden="true">
            {String(index + 1).padStart(2, "0")}
          </div>
          <div>
            <span
              className={`owner owner-${
                step.executor === "Coding agent"
                  ? "agent"
                  : step.executor === "Human operator"
                    ? "human"
                    : step.executor === "Traigent service"
                      ? "service"
                      : "verifier"
              }`}
            >
              {step.executor} executes
            </span>
            {step.humanGate === undefined ? null : (
              <span className="human-gate">{step.humanGate}</span>
            )}
            <h2>{step.label}</h2>
            <p>{step.detail}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}

function ScenarioCoverageMatrix({ slide }: { slide: SlideSpec }) {
  if (slide.scenarioMatrix === undefined) {
    return null;
  }
  return (
    <div className="matrix-wrap">
      <span className="matrix-scroll-hint" aria-hidden="true">
        Scroll sideways to see every column
      </span>
      <table className="starting-matrix scenario-coverage-matrix">
        <caption>
          Scenario family, material under test, expected route, and test
          scenario status
        </caption>
        <thead>
          <tr>
            <th scope="col">Scenario family</th>
            <th scope="col">Material and dataset archetype</th>
            <th scope="col">Behavior the scenario should exercise</th>
            <th scope="col">Test scenario status</th>
          </tr>
        </thead>
        <tbody>
          {slide.scenarioMatrix.map((row) => (
            <tr key={row.family}>
              <th scope="row">{row.family}</th>
              <td>{row.setup}</td>
              <td>{row.expectedRoute}</td>
              <td>
                <span className={`coverage coverage-${row.coverage}`}>
                  {coverageLabel(row.coverage)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StartingPointMatrix({ slide }: { slide: SlideSpec }) {
  if (slide.matrix === undefined) {
    return null;
  }
  return (
    <div className="matrix-wrap">
      <span className="matrix-scroll-hint" aria-hidden="true">
        Scroll sideways to see every column
      </span>
      <table className="starting-matrix">
        <caption>
          Starting condition, safest next step, and coverage status
        </caption>
        <thead>
          <tr>
            <th scope="col">Starting condition</th>
            <th scope="col">Safest justified next step</th>
            <th scope="col">Coverage today</th>
          </tr>
        </thead>
        <tbody>
          {slide.matrix.map((row) => (
            <tr key={row.startingPoint}>
              <th scope="row">{row.startingPoint}</th>
              <td>{row.safestNextStep}</td>
              <td>
                <span className={`coverage coverage-${row.coverage}`}>
                  {coverageLabel(row.coverage)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TestLayerMatrix({ slide }: { slide: SlideSpec }) {
  if (slide.testMatrix === undefined) {
    return null;
  }
  return (
    <div className="matrix-wrap">
      <span className="matrix-scroll-hint" aria-hidden="true">
        Scroll sideways to see every column
      </span>
      <table className="starting-matrix test-layer-matrix">
        <caption>
          Test layers and the claims each passing layer supports
        </caption>
        <thead>
          <tr>
            <th scope="col">Layer</th>
            <th scope="col">Action</th>
            <th scope="col">A pass supports</th>
            <th scope="col">Does not prove</th>
          </tr>
        </thead>
        <tbody>
          {slide.testMatrix.map((row) => (
            <tr key={row.layer}>
              <th scope="row">{row.layer}</th>
              <td>{row.action}</td>
              <td>{row.passSupports}</td>
              <td>{row.doesNotProve}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ScenarioCatalog({
  entry,
  view,
}: {
  entry: CatalogEntry;
  view: "setup-and-route" | "data-and-limits";
}) {
  const fields =
    view === "setup-and-route"
      ? [
          ["Starting state", entry.startingState],
          ["Present components", entry.components.join("; ")],
          ["Expected route", entry.expectedRouting],
          ["Tested layer", entry.testedLayer],
        ]
      : [
          ["Dataset", entry.dataset],
          ["Evaluator", entry.evaluator],
          ["Not proven", entry.notProven.join("; ")],
        ];
  return (
    <div className="catalog-grid" aria-label="Published scenario catalog">
      <section className="catalog-card">
        <div className="catalog-title">
          <h2>{entry.label}</h2>
          <span>Published</span>
        </div>
        <dl>
          {fields.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}

function Slide({ slide }: { slide: SlideSpec }) {
  const isHero = slide.kind === "hero";
  const slideRef = useRef<HTMLElement>(null);
  const eyebrow = displayEyebrow(slide);

  useLayoutEffect(() => {
    const fitParameters = new URLSearchParams(window.location.search);
    if (!fitParameters.has("fit-check")) {
      return;
    }
    const element = slideRef.current;
    if (element === null) {
      return;
    }
    const slideBounds = element.getBoundingClientRect();
    const selectors = [
      ".slide-heading",
      ".prompt-card",
      ".bullet-grid",
      ".metric-grid",
      ".journey",
      ".matrix-wrap",
      ".catalog-grid",
      ".slide-footer",
      ".slide-brand",
    ].join(",");
    const clipped = Array.from(element.querySelectorAll<HTMLElement>(selectors))
      .filter((child) => {
        const bounds = child.getBoundingClientRect();
        return (
          bounds.top < slideBounds.top - 1 ||
          bounds.left < slideBounds.left - 1 ||
          bounds.right > slideBounds.right + 1 ||
          bounds.bottom > slideBounds.bottom + 1
        );
      })
      .map((child) =>
        Array.from(child.classList)
          .map((name) => `.${name}`)
          .join(""),
      );
    const reasons = [
      Number(fitParameters.get("fit-width")) !== window.innerWidth ||
      Number(fitParameters.get("fit-height")) !== window.innerHeight
        ? `viewport mismatch ${window.innerWidth}x${window.innerHeight}`
        : "",
      element.scrollHeight > element.clientHeight + 1
        ? `slide vertical overflow ${element.scrollHeight}/${element.clientHeight}`
        : "",
      document.documentElement.scrollHeight > window.innerHeight + 1
        ? `page vertical overflow ${document.documentElement.scrollHeight}/${window.innerHeight}`
        : "",
      document.documentElement.scrollWidth > window.innerWidth + 1
        ? `page horizontal overflow ${document.documentElement.scrollWidth}/${window.innerWidth}`
        : "",
      ...clipped.map((className) => `clipped .${className}`),
    ].filter(Boolean);
    document.documentElement.dataset.fitStatus =
      reasons.length === 0 ? "pass" : "fail";
    document.documentElement.dataset.fitDetail = reasons.join("; ");
    document.documentElement.dataset.fitSlide = slide.id;
  }, [slide]);

  return (
    <article
      className={`slide slide-${slide.kind}`}
      aria-labelledby={`${slide.id}-title`}
      data-evidence-source-revision={slide.sourceRevision}
      ref={slideRef}
    >
      <div className="slide-glow" aria-hidden="true" />
      <div className="slide-brand" aria-hidden="true">
        <img src={traigentLogoPngDataUri} alt="" />
        <span>{brandName}</span>
      </div>
      <header className="slide-heading">
        <p className="eyebrow">
          <span aria-hidden="true" />
          {eyebrow}
        </p>
        <h1
          id={`${slide.id}-title`}
          className={isHero ? "hero-title" : undefined}
        >
          <HighlightedTitle slide={slide} />
        </h1>
        <p className="slide-body">{slide.body}</p>
      </header>

      {slide.quote !== undefined ? (
        <blockquote className="prompt-card">
          <span className="prompt-label">Paste into your coding agent</span>
          <code>{slide.quote}</code>
        </blockquote>
      ) : null}

      {slide.bullets.length > 0 ? (
        <ul className="bullet-grid">
          {slide.bullets.map((bullet) => (
            <li key={bullet}>
              <span aria-hidden="true" />
              {bullet}
            </li>
          ))}
        </ul>
      ) : null}

      <Metrics slide={slide} />
      <Journey slide={slide} />
      <StartingPointMatrix slide={slide} />
      <TestLayerMatrix slide={slide} />
      <ScenarioCoverageMatrix slide={slide} />
      {slide.kind === "catalog" &&
      slide.catalogSlug !== undefined &&
      slide.catalogView !== undefined &&
      presentation.catalog.some((entry) => entry.slug === slide.catalogSlug) ? (
        <ScenarioCatalog
          entry={presentation.catalog.find(
            (entry) => entry.slug === slide.catalogSlug,
          )!}
          view={slide.catalogView}
        />
      ) : null}

      <footer className="slide-footer">
        <EvidenceBadge slide={slide} />
        <span>{slide.evidence.join(" | ")}</span>
      </footer>
    </article>
  );
}

export function App() {
  const [slideIndex, setSlideIndex] = useState(initialSlideIndex);
  const [notesVisible, setNotesVisible] = useState(false);
  const mainRef = useRef<HTMLElement>(null);
  const slide = presentation.slides[slideIndex];

  const goTo = useCallback((nextIndex: number) => {
    const boundedIndex = Math.min(
      presentation.slides.length - 1,
      Math.max(0, nextIndex),
    );
    setSlideIndex(boundedIndex);
  }, []);

  const goPrevious = useCallback(
    () => goTo(slideIndex - 1),
    [goTo, slideIndex],
  );
  const goNext = useCallback(() => goTo(slideIndex + 1), [goTo, slideIndex]);

  useEffect(() => {
    window.history.replaceState(null, "", `#/${slide.id}`);
    document.title = `${slide.title} | ${presentation.title}`;
    mainRef.current?.focus({ preventScroll: true });
  }, [slide]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement
      ) {
        return;
      }
      if (event.key === "ArrowLeft" || event.key === "PageUp") {
        event.preventDefault();
        goPrevious();
      } else if (
        event.key === "ArrowRight" ||
        event.key === "PageDown" ||
        (event.key === " " && target === mainRef.current)
      ) {
        event.preventDefault();
        goNext();
      } else if (event.key === "Home") {
        event.preventDefault();
        goTo(0);
      } else if (event.key === "End") {
        event.preventDefault();
        goTo(presentation.slides.length - 1);
      } else if (event.key.toLocaleLowerCase("en") === "n") {
        event.preventDefault();
        setNotesVisible((visible) => !visible);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [goNext, goPrevious, goTo]);

  const progressLabel = useMemo(() => {
    if (slideIndex < coreSlideCount) {
      return `Core ${slideIndex + 1} of ${coreSlideCount}`;
    }
    return `Appendix ${slideIndex + 1 - coreSlideCount} of ${
      presentation.slides.length - coreSlideCount
    }`;
  }, [slideIndex]);

  return (
    <div className="presentation-shell">
      <a className="skip-link" href="#presentation-slide">
        Skip to slide content
      </a>
      <header className="topbar">
        <div className="brand" aria-label="Traigent">
          <img src={traigentLogoPngDataUri} alt="" aria-hidden="true" />
          <span>{brandName}</span>
        </div>
        <div className="deck-context">
          <span>First Run Scenarios</span>
          <span className="context-divider" aria-hidden="true" />
          <span>
            {slide.section === "appendix"
              ? "Technical appendix"
              : "Presales core"}
          </span>
        </div>
      </header>

      <main
        id="presentation-slide"
        className="stage"
        ref={mainRef}
        tabIndex={-1}
      >
        <Slide slide={slide} />
      </main>

      <nav className="controls" aria-label="Presentation controls">
        <button type="button" onClick={goPrevious} disabled={slideIndex === 0}>
          Previous
        </button>
        <div className="slide-picker" aria-label="Choose a slide">
          {presentation.slides.map((candidate, index) => (
            <button
              type="button"
              className={index === slideIndex ? "active" : undefined}
              aria-current={index === slideIndex ? "step" : undefined}
              aria-label={`Go to slide ${index + 1}: ${candidate.title}`}
              onClick={() => goTo(index)}
              key={candidate.id}
            >
              <span aria-hidden="true" />
            </button>
          ))}
        </div>
        <span className="progress" aria-live="polite">
          {progressLabel}
        </span>
        <button
          type="button"
          onClick={() => setNotesVisible((visible) => !visible)}
        >
          {notesVisible ? "Hide notes" : "Show notes"}
        </button>
        <button
          type="button"
          onClick={goNext}
          disabled={slideIndex === presentation.slides.length - 1}
        >
          Next
        </button>
      </nav>

      {notesVisible ? (
        <aside className="speaker-notes" aria-label="Speaker notes">
          <strong>Speaker notes</strong>
          <ul>
            {slide.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </aside>
      ) : null}
    </div>
  );
}
