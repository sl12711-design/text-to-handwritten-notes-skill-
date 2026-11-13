1/ PMF for daily sales
Let $X$ be the daily sales in dollars
Let $C \in \{1, 2\}$ be the number of customers contacted
$P(C = 1) = \frac{1}{3}$ and $P(C = 2) = \frac{2}{3}$
Each contact is an independent Bernoulli trial with $P(\text{sale}) = 0.1$ and $P(\text{no sale}) = 0.9$
The possible values for $X$ are \$0, \$50 000, \$100 000. Using the law of Total Probability
$$P(X = 0) = P(X = 0 \mid C = 1)P(C = 1) + P(X = 0 \mid C = 2)P(C = 2)$$
$$= 0.9 \times \frac{1}{3} + 0.9^2 \times \frac{2}{3} = 0.84$$
$$P(X = 50\,000) = (0.1)\left(\frac{1}{3}\right) + \binom{2}{1}(0.1)(0.9)\left(\frac{2}{3}\right)$$
$$= \frac{0.46}{3} \approx 0.1533$$
$$P(X = 100\,000) = (0.1)^2\left(\frac{2}{3}\right) = \frac{0.02}{3} \approx 0.0067$$

2) Mean and standard deviation
Let $Y = \frac{X}{50\,000}$ the number of sales
$$E(Y) = 0(0.84) + 1\left(\frac{0.46}{3}\right) + 2\left(\frac{0.02}{3}\right) = \frac{1}{6}$$
$$\mu = E(X) = 50\,000 \times E(Y) \approx 8\,333.33$$
$$E(Y^2) = 0^2(0.84) + 1^2\left(\frac{0.46}{3}\right) + 2^2\left(\frac{0.02}{3}\right) = 0.18$$
$$Var(Y) = E(Y^2) - [E(Y)]^2 = 0.18 - \left(\frac{1}{6}\right)^2 = \frac{137}{900}$$
$$\sigma = SD(X) = 50\,000\sqrt{\frac{137}{900}} \approx 19\,507.83$$
