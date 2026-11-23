import { useT } from '../i18n';
import styles from './FloatingLinks.module.css';

const TEMPLATE = 'openai-agents-starter-python';
const AGENT_LANG = 'python';

/**
 * Build the one-click deploy URL.
 *
 * On *.edgeone.dev (the public preview surface) we point to edgeone.ai;
 * everywhere else (Tencent Cloud console, local dev) we point to the
 * console domain so authenticated users land on the right tenant.
 */
function getDeployUrl(): string {
  const deployParams = `?template=${TEMPLATE}&from=within&fromAgent=1&agentLang=${AGENT_LANG}`;
  const edgeoneDeployUrl = `https://edgeone.ai/makers/new${deployParams}`;
  const cloudDeployUrl = `https://console.cloud.tencent.com/edgeone/makers/new${deployParams}`;

  if (typeof window === 'undefined') return edgeoneDeployUrl;
  return window.location.hostname.endsWith('.edgeone.dev') ? edgeoneDeployUrl : cloudDeployUrl;
}

/**
 * Floating rocket badge for one-click deploy. Pinned to the left of
 * the GitHub badge in the bottom-right viewport corner, sharing the
 * same neumorphic hover / press animations.
 */
export default function DeployLink() {
  const { t } = useT();
  const label = t('floatingLink.deploy');

  return (
    <div className={`${styles.dock} ${styles.dockDeploy}`}>
      <a
        href={getDeployUrl()}
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
          fill='none'
          stroke='currentColor'
          strokeWidth={1.8}
          strokeLinecap='round'
          strokeLinejoin='round'
          aria-hidden='true'
        >
          <path d='M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09Z' />
          <path d='M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2Z' />
          <path d='M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0' />
          <path d='M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5' />
        </svg>
      </a>
    </div>
  );
}
