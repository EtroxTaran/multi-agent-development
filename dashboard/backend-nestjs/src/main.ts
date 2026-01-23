import { NestFactory } from '@nestjs/core';
import {
  FastifyAdapter,
  NestFastifyApplication,
} from '@nestjs/platform-fastify';
import { ValidationPipe } from '@nestjs/common';
import { SwaggerModule, DocumentBuilder } from '@nestjs/swagger';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create<NestFastifyApplication>(
    AppModule,
    new FastifyAdapter({ logger: true }),
  );

  // Enable CORS
  app.enableCors({
    origin: true,
    credentials: true,
  });

  // Global validation pipe
  app.useGlobalPipes(
    new ValidationPipe({
      whitelist: true,
      transform: true,
      forbidNonWhitelisted: true,
    }),
  );

  // Swagger documentation
  const config = new DocumentBuilder()
    .setTitle('Conductor Dashboard API')
    .setDescription('REST API for the Conductor multi-agent orchestration dashboard')
    .setVersion('1.0.0')
    .addTag('projects', 'Project management endpoints')
    .addTag('workflow', 'Workflow control endpoints')
    .addTag('tasks', 'Task management endpoints')
    .addTag('agents', 'Agent status endpoints')
    .addTag('budget', 'Budget tracking endpoints')
    .addTag('chat', 'Chat interface endpoints')
    .build();
  const document = SwaggerModule.createDocument(app, config);
  SwaggerModule.setup('docs', app, document);

  const port = process.env.PORT || 8080;
  await app.listen(port, '0.0.0.0');
  console.log(`Conductor Dashboard API running on http://localhost:${port}`);
  console.log(`Swagger docs available at http://localhost:${port}/docs`);
}

bootstrap();
