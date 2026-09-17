const express = require('express');
const logger = require('./middleware/logger');
const app = express();
app.use(express.json());
const PORT = 3000;

app.get('/', (req, res) => {
  res.send('My Week 2 API!');
});

app.post('/user', (req, res) => {
  const { name, email } = req.body;
  res.send(`Hello, ${name}!`);
});

app.listen(PORT, () => {
  console.log(`Server running on http://localhost:${PORT}`);
}); 

