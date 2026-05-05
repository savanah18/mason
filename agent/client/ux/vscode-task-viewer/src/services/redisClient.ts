import * as vscode from 'vscode';
import { createClient, RedisClientType } from 'redis';

let redisClient: RedisClientType | null = null;

export async function initializeRedisClient(): Promise<void> {
  const config = vscode.workspace.getConfiguration('taskViewer.redis');
  const host = config.get<string>('host', 'localhost');
  const port = config.get<number>('port', 6379);
  const password = config.get<string>('password', '');
  const database = config.get<number>('database', 0);

  redisClient = createClient({
    host,
    port,
    password: password || undefined,
    database,
  } as any);

  redisClient.on('error', (err) => console.error('[Task Viewer Redis]', err));
  await redisClient.connect();
}

export function getRedisClient(): RedisClientType {
  if (!redisClient) {
    throw new Error('Redis client not initialized');
  }
  return redisClient;
}

export async function disconnectRedisClient(): Promise<void> {
  if (redisClient) {
    await redisClient.disconnect();
    redisClient = null;
  }
}
