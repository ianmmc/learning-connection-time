/**
 * Job Manager for Async Crawlee Operations
 *
 * Manages long-running mapping jobs with disk-based state persistence.
 * Enables progress tracking and resilience across restarts.
 */

import { promises as fs } from 'fs';
import * as path from 'path';
import { v4 as uuidv4 } from 'uuid';
import { logger } from './logger.js';
import { CrawleePageData } from './mapper.js';

const JOBS_DIR = path.join(process.cwd(), '..', '..', 'data', 'jobs');

export type JobPhase = 'queued' | 'crawling' | 'completed' | 'failed';

export interface JobStatus {
  jobId: string;
  phase: JobPhase;
  url: string;
  startedAt: string;
  updatedAt: string;
  completedAt?: string;
  pagesVisited: number;
  pagesQueued: number;
  pagesWithTimePatterns: number;
  pagesWithBellKeywords: number;
  error?: string;
  config: {
    maxRequests: number;
    maxDepth: number;
  };
}

export interface JobResult {
  status: JobStatus;
  pages: CrawleePageData[];
  isComplete: boolean;
}

/**
 * Ensure the jobs directory exists
 */
async function ensureJobsDir(): Promise<void> {
  await fs.mkdir(JOBS_DIR, { recursive: true });
}

/**
 * Get the directory path for a specific job
 */
function getJobDir(jobId: string): string {
  return path.join(JOBS_DIR, jobId);
}

/**
 * Create a new job and return its ID
 */
export async function createJob(
  url: string,
  config: { maxRequests: number; maxDepth: number }
): Promise<string> {
  await ensureJobsDir();

  const jobId = uuidv4();
  const jobDir = getJobDir(jobId);

  await fs.mkdir(jobDir, { recursive: true });

  const status: JobStatus = {
    jobId,
    phase: 'queued',
    url,
    startedAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    pagesVisited: 0,
    pagesQueued: 1, // Initial URL
    pagesWithTimePatterns: 0,
    pagesWithBellKeywords: 0,
    config,
  };

  await fs.writeFile(
    path.join(jobDir, 'status.json'),
    JSON.stringify(status, null, 2)
  );

  // Create empty pages file
  await fs.writeFile(path.join(jobDir, 'pages.jsonl'), '');

  logger.info(`Created job ${jobId} for ${url}`);
  return jobId;
}

/**
 * Update job status
 */
export async function updateJobStatus(
  jobId: string,
  updates: Partial<JobStatus>
): Promise<void> {
  const jobDir = getJobDir(jobId);
  const statusPath = path.join(jobDir, 'status.json');

  try {
    const currentStatus = JSON.parse(await fs.readFile(statusPath, 'utf-8')) as JobStatus;
    const newStatus: JobStatus = {
      ...currentStatus,
      ...updates,
      updatedAt: new Date().toISOString(),
    };

    await fs.writeFile(statusPath, JSON.stringify(newStatus, null, 2));
  } catch (error) {
    logger.error(`Failed to update job status for ${jobId}: ${(error as Error).message}`);
  }
}

/**
 * Append a page to the job's results
 */
export async function appendPage(jobId: string, page: CrawleePageData): Promise<void> {
  const jobDir = getJobDir(jobId);
  const pagesPath = path.join(jobDir, 'pages.jsonl');

  await fs.appendFile(pagesPath, JSON.stringify(page) + '\n');
}

/**
 * Mark a job as complete
 */
export async function completeJob(
  jobId: string,
  stats: {
    pagesVisited: number;
    pagesWithTimePatterns: number;
    pagesWithBellKeywords: number;
  }
): Promise<void> {
  const jobDir = getJobDir(jobId);

  await updateJobStatus(jobId, {
    phase: 'completed',
    completedAt: new Date().toISOString(),
    pagesQueued: 0,
    ...stats,
  });

  // Create completion flag file
  await fs.writeFile(path.join(jobDir, 'complete'), '');

  logger.info(`Job ${jobId} completed: ${stats.pagesVisited} pages`);
}

/**
 * Mark a job as failed
 */
export async function failJob(jobId: string, error: string): Promise<void> {
  await updateJobStatus(jobId, {
    phase: 'failed',
    completedAt: new Date().toISOString(),
    error,
  });

  logger.error(`Job ${jobId} failed: ${error}`);
}

/**
 * Get job status
 */
export async function getJobStatus(jobId: string): Promise<JobStatus | null> {
  const jobDir = getJobDir(jobId);
  const statusPath = path.join(jobDir, 'status.json');

  try {
    const content = await fs.readFile(statusPath, 'utf-8');
    return JSON.parse(content) as JobStatus;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
      return null;
    }
    throw error;
  }
}

/**
 * Get job results (pages)
 */
export async function getJobPages(jobId: string): Promise<CrawleePageData[]> {
  const jobDir = getJobDir(jobId);
  const pagesPath = path.join(jobDir, 'pages.jsonl');

  try {
    const content = await fs.readFile(pagesPath, 'utf-8');
    const lines = content.trim().split('\n').filter(line => line.length > 0);
    return lines.map(line => JSON.parse(line) as CrawleePageData);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
      return [];
    }
    throw error;
  }
}

/**
 * Check if a job is complete
 */
export async function isJobComplete(jobId: string): Promise<boolean> {
  const jobDir = getJobDir(jobId);
  const completePath = path.join(jobDir, 'complete');

  try {
    await fs.access(completePath);
    return true;
  } catch {
    return false;
  }
}

/**
 * Get full job result (status + pages)
 */
export async function getJobResult(jobId: string): Promise<JobResult | null> {
  const status = await getJobStatus(jobId);
  if (!status) return null;

  const pages = await getJobPages(jobId);
  const isComplete = await isJobComplete(jobId);

  return { status, pages, isComplete };
}

/**
 * List all jobs (for debugging/admin)
 */
export async function listJobs(): Promise<JobStatus[]> {
  await ensureJobsDir();

  try {
    const entries = await fs.readdir(JOBS_DIR, { withFileTypes: true });
    const jobs: JobStatus[] = [];

    for (const entry of entries) {
      if (entry.isDirectory()) {
        const status = await getJobStatus(entry.name);
        if (status) {
          jobs.push(status);
        }
      }
    }

    // Sort by start time, most recent first
    return jobs.sort((a, b) =>
      new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime()
    );
  } catch (error) {
    logger.error(`Failed to list jobs: ${(error as Error).message}`);
    return [];
  }
}

/**
 * Clean up old completed jobs (older than maxAge hours)
 */
export async function cleanupOldJobs(maxAgeHours: number = 24): Promise<number> {
  await ensureJobsDir();

  const cutoff = new Date(Date.now() - maxAgeHours * 60 * 60 * 1000);
  let cleaned = 0;

  try {
    const entries = await fs.readdir(JOBS_DIR, { withFileTypes: true });

    for (const entry of entries) {
      if (entry.isDirectory()) {
        const status = await getJobStatus(entry.name);
        if (status && status.completedAt) {
          const completedAt = new Date(status.completedAt);
          if (completedAt < cutoff) {
            await fs.rm(getJobDir(entry.name), { recursive: true });
            cleaned++;
          }
        }
      }
    }

    if (cleaned > 0) {
      logger.info(`Cleaned up ${cleaned} old jobs`);
    }
    return cleaned;
  } catch (error) {
    logger.error(`Failed to cleanup jobs: ${(error as Error).message}`);
    return 0;
  }
}
