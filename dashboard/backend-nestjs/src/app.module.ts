import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { AppController } from './app.controller';
import { ProjectsModule } from './projects/projects.module';
import { WorkflowModule } from './workflow/workflow.module';
import { TasksModule } from './tasks/tasks.module';
import { AgentsModule } from './agents/agents.module';
import { BudgetModule } from './budget/budget.module';
import { ChatModule } from './chat/chat.module';
import { WebsocketModule } from './websocket/websocket.module';
import { OrchestratorClientModule } from './orchestrator-client/orchestrator-client.module';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      envFilePath: ['.env.local', '.env'],
    }),
    OrchestratorClientModule,
    ProjectsModule,
    WorkflowModule,
    TasksModule,
    AgentsModule,
    BudgetModule,
    ChatModule,
    WebsocketModule,
  ],
  controllers: [AppController],
})
export class AppModule {}
