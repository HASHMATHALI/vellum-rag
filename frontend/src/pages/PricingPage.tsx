import React from 'react';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { useNavigate } from 'react-router-dom';
import { Check } from 'lucide-react';

export const PricingPage: React.FC = () => {
  const navigate = useNavigate();

  const plans = [
    {
      name: 'Community/Free',
      price: '$0',
      period: 'forever',
      description: 'Ideal for individuals to parse personal files or experiment with semantic search.',
      features: [
        'Upload up to 10 documents',
        'Max 10MB per file size limit',
        'Standard Semantic search retrieval',
        'Conversational history logs',
        'Shared Llama model access'
      ],
      buttonText: 'Get Started Free',
      variant: 'secondary' as const
    },
    {
      name: 'Developer/Pro',
      price: '$29',
      period: 'per month',
      description: 'Great for developers and startups looking to integrate AI search into external apps.',
      features: [
        'Upload up to 5,000 documents',
        'Max 50MB per file size limit',
        'Semantic, MMR, & Hybrid retrievals',
        'Generate REST API integration keys',
        'Priority queue background processing',
        'Access to dedicated fast LLM inference'
      ],
      buttonText: 'Start Pro Trial',
      variant: 'primary' as const,
      popular: true
    },
    {
      name: 'Enterprise',
      price: 'Custom',
      period: 'custom pricing',
      description: 'Tailored solutions for large scale datasets requiring self-hosted options.',
      features: [
        'Unlimited document counts',
        'Supports large gigabyte uploads',
        'Custom local embedders & domain weights',
        'Dedicated isolated cloud deployments',
        'Active SLA support & system monitoring',
        'Single Sign-On (SSO) integration'
      ],
      buttonText: 'Contact Sales',
      variant: 'secondary' as const
    }
  ];

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
      <div className="text-center max-w-2xl mx-auto mb-16">
        <h1 className="font-display text-4xl sm:text-5xl font-extrabold mb-4">
          Simple, Transparent <span className="gradient-text">Pricing Plans</span>
        </h1>
        <p className="text-gray-600 dark:text-dark-muted leading-relaxed">
          Scale your semantic search workspace. Start experimenting for free, then upgrade to access developers features and API integrations.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-8 items-stretch mb-12">
        {plans.map((plan) => (
          <Card 
            key={plan.name}
            hoverEffect 
            className={`p-8 flex flex-col justify-between relative border-gray-200/50 dark:border-white/5 bg-white dark:bg-dark-card ${
              plan.popular ? 'ring-2 ring-brand-500 shadow-xl' : ''
            }`}
          >
            {plan.popular && (
              <span className="absolute top-0 right-6 -translate-y-1/2 px-3 py-1 rounded-full text-xs font-bold bg-brand-500 text-white uppercase tracking-wider">
                Most Popular
              </span>
            )}

            <div>
              <h3 className="font-display font-bold text-2xl mb-2">{plan.name}</h3>
              <p className="text-sm text-gray-500 dark:text-dark-muted mb-6 leading-relaxed min-h-[48px]">{plan.description}</p>
              
              <div className="flex items-baseline gap-1 mb-8">
                <span className="text-4xl font-extrabold font-display">{plan.price}</span>
                <span className="text-sm text-gray-500 dark:text-dark-muted">/{plan.period}</span>
              </div>

              <div className="h-px bg-gray-200 dark:bg-dark-border mb-8" />

              <ul className="space-y-4 mb-8">
                {plan.features.map((feat) => (
                  <li key={feat} className="flex items-start gap-3 text-sm">
                    <Check className="w-5 h-5 text-emerald-500 shrink-0 mt-0.5" />
                    <span className="text-gray-600 dark:text-dark-muted leading-relaxed">{feat}</span>
                  </li>
                ))}
              </ul>
            </div>

            <Button 
              variant={plan.variant} 
              onClick={() => navigate('/login')}
              className="w-full"
            >
              {plan.buttonText}
            </Button>
          </Card>
        ))}
      </div>
    </div>
  );
};


