import '@mantine/core/styles.css';
import '@mantine/charts/styles.css';
import '@mantine/dates/styles.css';
import '@mantine/notifications/styles.css';
import './app.css';

import 'dayjs/locale/es';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { MantineProvider, createTheme, type MantineColorsTuple } from '@mantine/core';
import { DatesProvider } from '@mantine/dates';
import { Notifications } from '@mantine/notifications';
import { App } from './App';

// Azul marino Royal Marina + acento mar.
const marina: MantineColorsTuple = [
  '#eef3fb', '#d9e2f2', '#afc3e6', '#82a2da', '#5d86cf', '#4574c9',
  '#386bc7', '#2a5ab0', '#21509e', '#14284b',
];

const theme = createTheme({
  primaryColor: 'marina',
  primaryShade: { light: 7, dark: 5 },
  colors: { marina },
  fontFamily: 'Inter, "Segoe UI", system-ui, -apple-system, Roboto, sans-serif',
  headings: { fontFamily: 'Inter, "Segoe UI", system-ui, sans-serif', fontWeight: '650' },
  defaultRadius: 'md',
  components: {
    Card: { defaultProps: { withBorder: true, radius: 'lg', padding: 'lg' } },
    Paper: { defaultProps: { radius: 'lg' } },
    Table: { defaultProps: { verticalSpacing: 'sm', highlightOnHover: true } },
  },
});

createRoot(document.getElementById('root')!).render(
  <MantineProvider theme={theme} defaultColorScheme="light">
    <DatesProvider settings={{ locale: 'es', firstDayOfWeek: 1 }}>
      <Notifications position="top-right" />
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </DatesProvider>
  </MantineProvider>,
);