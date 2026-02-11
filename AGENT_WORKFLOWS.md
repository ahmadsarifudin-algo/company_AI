# Company Agent Workflows

## High-Level System Architecture

This diagram illustrates the core "Operating System" architecture used across all departments (Tech, Finance, HR, Sales, Marketing, Legal, BizDev).

```mermaid
graph TD
    User([User]) -->|Request| Gateway[Agent Gateway]
    
    subgraph "Core Agent System"
        Gateway -->|Auth & RBAC| Supervisor[Supervisor Agent]
        Supervisor -->|Plan JSON| Queue[Work Queue]
        
        subgraph "Execution Layer"
            Queue -->|Task| Agent1[Specialist Agent A]
            Queue -->|Task| Agent2[Specialist Agent B]
            Queue -->|Task| Agent3[Specialist Agent C]
            
            Agent1 <-->|Execute| Sandbox[(Tool Sandbox)]
            Agent2 <-->|Execute| Sandbox
            Agent3 <-->|Execute| Sandbox
        end
        
        Agent1 -->|Output| Store[(Artifact Store)]
        Agent2 -->|Output| Store
        Agent3 -->|Output| Store
    end
    
    subgraph "Governance & Compliance"
        Gateway -.->|Log| Audit[(Audit Log)]
        Supervisor -.->|Log| Audit
        Agent1 -.->|Log| Audit
        Agent2 -.->|Log| Audit
        Agent3 -.->|Log| Audit
    end

    Store -->|Final Artifacts| User
```

## Department Specific Workflows

### 1. Tech Development Workflow
Focus: Feature Delivery & Quality Gates

```mermaid
sequenceDiagram
    participant User
    participant Gateway
    participant Supervisor
    participant Agents as Dev/QA/Sec Agents
    participant Tools as Git/CI/Cloud
    participant Store as Artifact Store

    User->>Gateway: Submit Feature Request
    Gateway->>Supervisor: Validate & Forward
    Supervisor->>Supervisor: Generate Dev Plan (JSON)
    
    par Parallel Execution
        Supervisor->>Agents: Assign Backend Tasks
        Supervisor->>Agents: Assign Frontend Tasks
    end

    loop Development Cycle
        Agents->>Tools: Write Code / Run Tests
        Tools-->>Agents: Build/Test Results
        Agents->>Store: Store PR / Test Report
    end
    
    Agents->>Supervisor: Task Complete
    Supervisor->>Gateway: Trigger Quality Gate
    Gateway-->>User: Request Review/Approval
```

### 2. Finance Workflow
Focus: Accuracy, Compliance & Audit Trails

```mermaid
sequenceDiagram
    participant User as Finance Team
    participant Gateway
    participant Supervisor
    participant Agents as Accounting/Audit Agents
    participant Ledger as Immutable Ledger
    participant Store as Fin. Doc Store

    User->>Gateway: Submit Budget/Audit Request
    Gateway->>Gateway: Strict RBAC Check
    Gateway->>Supervisor: Forward Request
    
    Supervisor->>Agents: Assign Reconciliation/Audit Tasks
    
    loop Compliance Check
        Agents->>Ledger: Read Transaction Data (Read-Only)
        Agents->>Agents: Verify vs Policy
        Agents->>Ledger: Log Action (Immutable)
    end
    
    Agents->>Store: Generate Financial Report
    Store-->>User: Deliver Report for Approval
```

### 3. HR Workflow
Focus: Privacy & Data Segregation

```mermaid
sequenceDiagram
    participant User as HR Mgr
    participant Gateway
    participant Supervisor
    participant Agents as Recruit/Payroll Agents
    participant HRIS as Secure HRIS
    
    User->>Gateway: Request Recruitment/Payroll
    Gateway->>Gateway: Verify Data Access Level
    Gateway->>Supervisor: Forward Request
    
    Supervisor->>Agents: Assign Tasks (Anonymized if needed)
    
    alt Recruitment
        Agents->>HRIS: Screen Candidates
    else Payroll
        Agents->>HRIS: Validate Payroll Data
    end
    
    Agents->>Supervisor: Submit Draft
    Supervisor->>User: Request Approval (Sensitive Action)
```

### 4. Sales Workflow
Focus: Revenue & Speed

```mermaid
sequenceDiagram
    participant User as Sales Rep
    participant Gateway
    participant Supervisor
    participant Agents as Lead/Pricing Agents
    participant CRM
    
    User->>Gateway: Request Lead Score / Pricing
    Gateway->>Supervisor: Analyze Request
    
    par Sales Optimization
        Supervisor->>Agents: Score Leads
        Supervisor->>Agents: Optimize Pricing
    end
    
    Agents->>CRM: Update Deal Status / Notes
    Agents->>User: Provide Recommendations
```

### 5. Digital Marketing Workflow
Focus: Brand Presence, Content & ROI

```mermaid
sequenceDiagram
    participant User as Marketing Head
    participant Gateway
    participant Supervisor
    participant Agents as Content/Social/Analytics Agents
    participant CMS as CMS & Social APIs
    
    User->>Gateway: Request Campaign Launch
    Gateway->>Supervisor: Validate & Forward
    
    par Content Production
        Supervisor->>Agents: Generate Copy (Content Creator)
        Supervisor->>Agents: Create Visuals (Content Maker)
    end
    
    Agents->>CMS: Publish to Social / CMS
    Agents->>Agents: Monitor Engagement (Social Media Agent)
    Agents->>Supervisor: Campaign Analytics Report
    Supervisor-->>User: ROI & Performance Dashboard
```

### 6. Legal Workflow
Focus: Compliance, Contracts & Risk Mitigation

```mermaid
sequenceDiagram
    participant User as Legal Head
    participant Gateway
    participant Supervisor
    participant Agents as Contract/Compliance/IP Agents
    participant LegalDB as Legal Research DB
    
    User->>Gateway: Submit Legal Request
    Gateway->>Gateway: Strict Access Check
    Gateway->>Supervisor: Forward Request
    
    alt Contract Task
        Supervisor->>Agents: Draft / Review Contract
        Agents->>LegalDB: Check Standard Clauses Library
        Agents->>Supervisor: Submit Draft for Review
    else Compliance Task
        Supervisor->>Agents: Check Regulatory Changes
        Agents->>LegalDB: Query Regulation Database
        Agents->>Supervisor: Compliance Report
    end
    
    Supervisor->>User: Request Human Sign-off (Mandatory)
```

### 7. Strategic & Business Development Workflow
Focus: Market Intelligence & Growth Strategy

```mermaid
sequenceDiagram
    participant User as BizDev Director
    participant Gateway
    participant Supervisor
    participant Agents as Market/Partnership/Strategy Agents
    participant Data as Market Data APIs
    
    User->>Gateway: Submit Strategic Initiative
    Gateway->>Supervisor: Analyze & Decompose
    
    par Market Intelligence
        Supervisor->>Agents: Research Market (Market Research Agent)
        Supervisor->>Agents: Analyze Competitors (Competitive Intel Agent)
    end
    
    Agents->>Data: Pull Market Data (Crunchbase, Statista)
    Agents->>Agents: Build Financial Model (Business Modeling Agent)
    Agents->>Supervisor: Strategy Recommendation
    Supervisor-->>User: Present Options + Board Deck
```

### 8. Cross-Department Coordination
Focus: Multi-Department Task Resolution

```mermaid
sequenceDiagram
    participant Sales as Sales Supervisor
    participant GS as Global Supervisor
    participant Legal as Legal Supervisor
    participant Finance as Finance Supervisor
    
    Sales->>GS: New Partnership Deal — Need Legal + Finance Review
    
    par Cross-Department Routing
        GS->>Legal: Route Contract for Review
        GS->>Finance: Route Budget Approval
    end
    
    Legal-->>GS: Contract Approved (with amendments)
    Finance-->>GS: Budget Approved
    GS-->>Sales: Deal Cleared — Proceed
```
