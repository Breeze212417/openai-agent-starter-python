import { useT } from '../i18n';
import styles from './FloatingLinks.module.css';

const REPO_URL = 'https://github.com/TencentEdgeOne/openai-agent-starter-python';

/**
 * Floating GitHub badge anchored to the bottom-right viewport corner.
 * Uses the shared neumorphic badge styling (dock entrance, hover lift,
 * icon tilt, press state) from FloatingLinks.module.css. A localised
 * tooltip floats above the badge on hover/focus.
 */
export default function GitHubLink() {
  const { t } = useT();
  const label = t('floatingLink.github');

  return (
    <div className={`${styles.dock} ${styles.dockGithub}`}>
      <a
        href={REPO_URL}
        target='_blank'
        rel='noopener noreferrer'
        aria-label={label}
        className={styles.fab}
      >
        <span role='tooltip' className={styles.tooltip}>{label}</span>
        <svg
          viewBox='0 0 24 24'
          width={22}
          height={22}
          fill='currentColor'
          aria-hidden='true'
        >
          <path d='M12 .5C5.73.5.5 5.73.5 12c0 5.08 3.29 9.39 7.86 10.91.58.1.79-.25.79-.56 0-.28-.01-1.02-.02-2-3.2.7-3.87-1.54-3.87-1.54-.52-1.32-1.27-1.67-1.27-1.67-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.18 1.76 1.18 1.02 1.76 2.69 1.25 3.35.96.1-.74.4-1.25.73-1.54-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.29 1.18-3.1-.12-.29-.51-1.46.11-3.05 0 0 .96-.31 3.16 1.18a10.94 10.94 0 0 1 5.75 0c2.2-1.49 3.16-1.18 3.16-1.18.62 1.59.23 2.76.11 3.05.74.81 1.18 1.84 1.18 3.1 0 4.42-2.7 5.4-5.27 5.68.42.36.79 1.07.79 2.16 0 1.56-.01 2.81-.01 3.19 0 .31.21.67.8.56C20.21 21.39 23.5 17.07 23.5 12 23.5 5.73 18.27.5 12 .5z' />
        </svg>
      </a>
    </div>
  );
}
