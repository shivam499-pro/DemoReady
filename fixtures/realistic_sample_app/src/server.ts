import express, { Request, Response } from 'express';

const app = express();

// Dedicated health endpoint for service liveness probe
app.get('/health', (req: Request, res: Response) => {
    res.status(200).json({
        status: 'UP',
        timestamp: new Date().toISOString(),
    });
});

app.get('/api/v1/products', (req: Request, res: Response) => {
    res.json([]);
});

export default app;
